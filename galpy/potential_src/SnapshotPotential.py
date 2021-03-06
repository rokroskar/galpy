try: 
    from pynbody import grav_omp
except ImportError: 
    raise ImportError("This class is designed to work with pynbody snapshots -- obtain from pynbody.github.io")

import pynbody
from pynbody import grav_omp
import numpy as np
from Potential import Potential
import hashlib
from scipy.misc import derivative
import interpRZPotential
from scipy import interpolate 
from os import system
from galpy.util import multi

class SnapshotPotential(Potential):
    """Create a snapshot potential object. The potential and forces are 
    calculated as needed through the _evaluate and _Rforce methods. 
    Requires an installation of [pynbody](http://pynbody.github.io).
    
    `_evaluate` and `_Rforce` calculate a hash for the array of points
    that is passed in by the user. The hash and corresponding
    potential/force arrays are stored -- if a subsequent request
    matches a previously computed hash, the previous results are
    returned and note recalculated.
    
    **Input**:
    
    *s* : a simulation snapshot loaded with pynbody

    **Optional Keywords**:
    
    *num_threads* (4): number of threads to use for calculation

    """

    def __init__(self, s, num_threads=pynbody.config['number_of_threads']) : 
        Potential.__init__(self,amp=1.0)

        self._s = s
        self._point_hash = {}
        self._num_threads = num_threads
    
    def _evaluate(self, R,z,phi=None,t=None,dR=None,dphi=None) : 
        pot, acc = self._setup_potential(R,z)
        return pot
        
    def _Rforce(self, R,z,phi=None,t=None,dR=None,dphi=None) : 
        pot, acc = self._setup_potential(R,z)
        return acc[:,0]

    def _setup_potential(self, R, z, use_pkdgrav = False) : 
        from galpy.potential import vcirc
        # cast the points into arrays for compatibility
        if isinstance(R,float) : 
            R = np.array([R])
        if isinstance(z, float) : 
            z = np.array([z])

        # compute the hash for the requested grid
        new_hash = hashlib.md5(np.array([R,z])).hexdigest()

        # if we computed for these points before, return; otherwise compute
        if new_hash in self._point_hash : 
            pot, r_acc = self._point_hash[new_hash]

#        if use_pkdgrav :
            

        else : 
            # set up the four points per R,z pair to mimic axisymmetry
            points = np.zeros((len(R),len(z),4,3))
        
            for i in xrange(len(R)) :
                for j in xrange(len(z)) : 
                    points[i,j] = [(R[i],0,z[j]),
                                   (0,R[i],z[j]),
                                   (-R[i],0,z[j]),
                                   (0,-R[i],z[j])]

            points_new = points.reshape(points.size/3,3)
            pot, acc = grav_omp.direct(self._s,points_new,num_threads=self._num_threads)

            pot = pot.reshape(len(R)*len(z),4)
            acc = acc.reshape(len(R)*len(z),4,3)

            # need to average the potentials
            if len(pot) > 1:
                pot = pot.mean(axis=1)
            else : 
                pot = pot.mean()


            # get the radial accelerations
            r_acc = np.zeros((len(R)*len(z),2))
            rvecs = [(1.0,0.0,0.0),
                     (0.0,1.0,0.0),
                     (-1.0,0.0,0.0),
                     (0.0,-1.0,0.0)]
        
            # reshape the acc to make sure we have a leading index even
            # if we are only evaluating a single point, i.e. we have
            # shape = (1,4,3) not (4,3)
            acc = acc.reshape((len(r_acc),4,3))

            for i in xrange(len(R)) : 
                for j,rvec in enumerate(rvecs) : 
                    r_acc[i,0] += acc[i,j].dot(rvec)
                    r_acc[i,1] += acc[i,j,2]
            r_acc /= 4.0
            
            # store the computed values for reuse
            self._point_hash[new_hash] = [pot,r_acc]

        return pot, r_acc


class InterpSnapshotPotential(interpRZPotential.interpRZPotential) : 
    """
    Interpolated potential extracted from a simulation output. 

    
    
    """

    
    def __init__(self, s, 
                 rgrid=(0.01,2.,101), zgrid=(0.,0.2,101), 
                 interpepifreq = False, interpverticalfreq = False, interpPot = True,
                 enable_c = True, logR = False, zsym = True, 
                 numcores=pynbody.config['number_of_threads'], use_pkdgrav = False) : 
        
        # inititalize using the base class
        Potential.__init__(self,amp=1.0)

        # other properties
        self._numcores = numcores
        self._s = s 

        # the interpRZPotential class sets these flags
        self._enable_c = enable_c
        self.hasC = True
                
        # set up the flags for interpolated quantities
        # since the potential and force are always calculated together, 
        # set the force interpolations to true if potential is true and 
        # vice versa
        self._interpPot = interpPot or interpRforce or interpzforce
        self._interpRforce = self._interpPot
        self._interpzforce = self._interpPot
        self._interpvcirc = self._interpPot
        
        # these require additional calculations so set them seperately
        self._interpepifreq = interpepifreq
        self._interpverticalfreq = interpverticalfreq

        # make the potential accessible at points beyond the grid
        self._origPot = SnapshotPotential(s, numcores)

        # setup the grid
        self._zsym = zsym
        self._logR = logR
        
        self._rgrid = np.linspace(*rgrid)
        if logR : 
            self._rgrid = np.exp(self._rgrid)
            self._logrgrid = np.log(self._rgrid)
            rs = self._logrgrid
        else : 
            rs = self._rgrid

        self._zgrid = np.linspace(*zgrid)

        # calculate the grids
        self._setup_potential(self._rgrid,self._zgrid,use_pkdgrav=use_pkdgrav)

        if enable_c and interpPot: 
            self._potGrid_splinecoeffs    = interpRZPotential.calc_2dsplinecoeffs_c(self._potGrid)
            self._rforceGrid_splinecoeffs = interpRZPotential.calc_2dsplinecoeffs_c(self._rforceGrid)
            self._zforceGrid_splinecoeffs = interpRZPotential.calc_2dsplinecoeffs_c(self._zforceGrid)

        else :
            self._potInterp= interpolate.RectBivariateSpline(rs,
                                                             self._zgrid,
                                                             self._potGrid,
                                                             kx=3,ky=3,s=0.)
            self._rforceInterp= interpolate.RectBivariateSpline(rs,
                                                                self._zgrid,
                                                                self._rforceGrid,
                                                                kx=3,ky=3,s=0.)
            self._zforceInterp= interpolate.RectBivariateSpline(rs,
                                                                self._zgrid,
                                                                self._zforceGrid,
                                                                kx=3,ky=3,s=0.)
        if interpepifreq:
            self._R2interp = interpolate.RectBivariateSpline(rs,
                                                             self._zgrid,
                                                             self._R2derivGrid,
                                                             kx=3,ky=3,s=0.)
            
        if interpverticalfreq: 
            self._z2interp = interpolate.RectBivariateSpline(rs,
                                                             self._zgrid,
                                                             self._z2derivGrid,
                                                             kx=3,ky=3,s=0.)
         
        # setup the derived quantities
        if interpPot: 
            self._vcircGrid = np.sqrt(self._rgrid*(-self._rforceGrid[:,0]))
            self._vcircInterp = interpolate.InterpolatedUnivariateSpline(rs, self._vcircGrid, k=3)
        
        if interpepifreq: 
            self._epifreqGrid = np.sqrt(self._R2derivGrid[:,0] - 3./self._rgrid*self._rforceGrid[:,0])
            self._epifreqInterp = interpolate.InterpolatedUnivariateSpline(rs, self._epifreqGrid, k=3)
            
        if interpverticalfreq:
            self._verticalfreqGrid = np.sqrt(np.abs(self._z2derivGrid[:,0]))
            self._verticalfreqInterp = interpolate.InterpolatedUnivariateSpline(rs, self._verticalfreqGrid, k=3)

        
    def _setup_potential(self, R, z, use_pkdgrav = False, dr = 0.01) : 
        """
        
        Calculates the potential and force grids for the snapshot for
        use with other galpy functions.
        
        **Input**:

        *R*: R grid coordinates 
        
        *z*: z grid coordinates

        **Optional Keywords**: 
        
        *use_pkdgrav*: (False) whether to use pkdgrav for the gravity
         calculation

        *dr*: (0.01) offset to use for the gradient calculation - the
         points are positioned at +/- dr from the central point
         
        """

        from galpy.potential import vcirc

        # cast the points into arrays for compatibility
        if isinstance(R,float) : 
            R = np.array([R])
        if isinstance(z, float) : 
            z = np.array([z])

        # set up the four points per R,z pair to mimic axisymmetry
        points = np.zeros((len(R),len(z),4,3))
        
        for i in xrange(len(R)) :
            for j in xrange(len(z)) : 
                points[i,j] = [(R[i],0,z[j]),
                               (0,R[i],z[j]),
                               (-R[i],0,z[j]),
                               (0,-R[i],z[j])]

        points_new = points.reshape(points.size/3,3)
        self.points = points_new

        # set up the points to calculate the second derivatives
        zgrad_points = np.zeros((len(points_new)*2,3))
        rgrad_points = np.zeros((len(points_new)*2,3))
        for i,p in enumerate(points_new) : 
            zgrad_points[i*2] = p
            zgrad_points[i*2][2] -= dr
            zgrad_points[i*2+1] = p
            zgrad_points[i*2+1][2] += dr
            
            rgrad_points[i*2] = p
            rgrad_points[i*2][:2] -= p[:2]/np.sqrt(np.dot(p[:2],p[:2]))*dr
            rgrad_points[i*2+1] = p
            rgrad_points[i*2+1][:2] += p[:2]/np.sqrt(np.dot(p[:2],p[:2]))*dr
                        

        if use_pkdgrav :
            raise RuntimeError("using pkdgrav not currently implemented")
            sn = pynbody.snapshot._new(len(self._s.d)+len(self._s.g)+len(self._s.s)+len(points_new))
            print "setting up %d grid points"%(len(points_new))
            #sn['pos'][0:len(self.s)] = self.s['pos']
            #sn['mass'][0:len(self.s)] = self.s['mass']
            #sn['phi'] = 0.0
            #sn['eps'] = 1e3
            #sn['eps'][0:len(self.s)] = self.s['eps']
            #sn['vel'][0:len(self.s)] = self.s['vel']
            #sn['mass'][len(self.s):] = 1e-10
            sn['pos'][len(self._s):] = points_new
            sn['mass'][len(self._s):] = 0.0
            
                
            sn.write(fmt=pynbody.tipsy.TipsySnap, filename='potgridsnap')
            command = '~/bin/pkdgrav2_pthread -sz %d -n 0 +std -o potgridsnap -I potgridsnap +potout +overwrite %s'%(self._numcores, self._s._paramfile['filename'])
            print command
            system(command)
            sn = pynbody.load('potgridsnap')
            acc = sn['accg'][len(self._s):].reshape(len(R)*len(z),4,3)
            pot = sn['pot'][len(self._s):].reshape(len(R)*len(z),4)
            

        else : 
            
            if self._interpPot: 
                pot, acc = grav_omp.direct(self._s,points_new,num_threads=self._numcores)

                pot = pot.reshape(len(R)*len(z),4)
                acc = acc.reshape(len(R)*len(z),4,3)

                # need to average the potentials
                if len(pot) > 1:
                    pot = pot.mean(axis=1)
                else : 
                    pot = pot.mean()


                # get the radial accelerations
                rz_acc = np.zeros((len(R)*len(z),2))
                rvecs = [(1.0,0.0,0.0),
                         (0.0,1.0,0.0),
                         (-1.0,0.0,0.0),
                         (0.0,-1.0,0.0)]
        
                # reshape the acc to make sure we have a leading index even
                # if we are only evaluating a single point, i.e. we have
                # shape = (1,4,3) not (4,3)
                acc = acc.reshape((len(rz_acc),4,3))

                for i in xrange(len(R)*len(z)) : 
                    for j,rvec in enumerate(rvecs) : 
                        rz_acc[i,0] += acc[i,j].dot(rvec)
                        rz_acc[i,1] += acc[i,j,2]
                rz_acc /= 4.0
            
                self._potGrid = pot.reshape((len(R),len(z)))
                self._rforceGrid = rz_acc[:,0].reshape((len(R),len(z)))
                self._zforceGrid = rz_acc[:,1].reshape((len(R),len(z)))

            # compute the force gradients

            # first get the accelerations
            if self._interpverticalfreq : 
                zgrad_pot, zgrad_acc = grav_omp.direct(self._s,zgrad_points,num_threads=self._numcores)
                # each point from the points used above for pot and acc is straddled by 
                # two points to get the gradient across it. Compute the gradient by 
                # using a finite difference 

                zgrad = np.zeros(len(points_new))
                
                # do a loop through the pairs of points -- reshape the array
                # so that each item is the pair of acceleration vectors
                # then calculate the gradient from the two points
                for i,zacc in enumerate(zgrad_acc.reshape((len(zgrad_acc)/2,2,3))) :
                    zgrad[i] = ((zacc[1]-zacc[0])/(dr*2.0))[2]
                
                # reshape the arrays
                self._z2derivGrid = zgrad.reshape((len(zgrad)/4,4)).mean(axis=1).reshape((len(R),len(z)))

            # do the same for the radial component
            if self._interpepifreq:
                rgrad_pot, rgrad_acc = grav_omp.direct(self._s,rgrad_points,num_threads=self._numcores)
                rgrad = np.zeros(len(points_new))

                for i,racc in enumerate(rgrad_acc.reshape((len(rgrad_acc)/2,2,3))) :
                    point = points_new[i]
                    point[2] = 0.0
                    rvec = point/np.sqrt(np.dot(point,point))
                    rgrad_vec = (np.dot(racc[1],rvec)-
                                 np.dot(racc[0],rvec)) / (dr*2.0)
                    rgrad[i] = rgrad_vec
                
                self._R2derivGrid = rgrad.reshape((len(rgrad)/4,4)).mean(axis=1).reshape((len(R),len(z)))


    
    
    def _R2deriv(self,R,Z,phi=0.,t=0.): 
        if not phi == 0.0 or not t == 0.0 : 
            raise RuntimeError("Only axisymmetric potentials are supported")
        if self._zsym: Z = np.abs(Z)
        return self._R2interp(R,Z)

    def _z2deriv(self,R,Z,phi=None,t=None):
        if not phi == 0.0 or not t == 0.0 : 
            raise RuntimeError("Only axisymmetric potentials are supported")
        if self._zsym: Z = np.abs(Z)
        return self._z2interp(R,Z)

    def normalize(self, R0=8.0) :
        """ 

        Normalize all positions by R0 and velocities by Vc(R0).  
        
        If :class:`~scipy.interpolate.RectBivariateSpline` or
        :class:`~scipy.interpolate.InterpolatedUnivariateSpline` are
        used, redefine them for use with the rescaled coordinates.  
        
        To undo the normalization, call
        :func:`~galpy.potential.SnapshotPotential.InterpSnapshotPotential.denormalize`.

        """

        Vc0 = self.vcirc(R0)
        Phi0 = np.abs(self.Rforce(R0,0.0))

        self._normR0 = R0
        self._normVc0 = Vc0
        self._normPhi0 = Phi0

        # rescale the simulation 
        self._posunit = self._s['pos'].units
        self._velunit = self._s['vel'].units
        self._s['pos'].convert_units('%s kpc'%R0)
        self._s['vel'].convert_units('%s km s**-1'%Vc0)
        
        
        # rescale the grid
        self._rgrid /= R0
        if self._logR: 
            self._logrgrid -= np.log(R0)
            rs = self._logrgrid
        else : 
            rs = self._rgrid

        self._zgrid /= R0

        # rescale the potential 
        self._amp /= Phi0        

        self._savedsplines = {}
        
        # rescale anything using splines
        if not self._enable_c and self._interpPot : 
            for spline,name in zip([self._potInterp, self._rforceInterp, self._zforceInterp],
                                    ["pot", "rforce", "zforce"]): 
                self._savedsplines[name] = spline
            
            self._potInterp= interpolate.RectBivariateSpline(rs, self._zgrid, self._potGrid, kx=3,ky=3,s=0.)
            self._rforceInterp= interpolate.RectBivariateSpline(rs, self._zgrid, self._rforceGrid, kx=3,ky=3,s=0.)
            self._zforceInterp= interpolate.RectBivariateSpline(rs, self._zgrid, self._zforceGrid, kx=3,ky=3,s=0.)
        
        if self._interpPot : 
            self._savedsplines['vcirc'] = self._vcircInterp
            self._vcircInterp = interpolate.InterpolatedUnivariateSpline(rs, self._vcircGrid/Vc0, k=3)

        if self._interpepifreq:
            self._savedsplines['R2deriv'] = self._R2interp
            self._savedsplines['epifreq'] = self._epifreqInterp
            self._R2interp = interpolate.RectBivariateSpline(rs,
                                                             self._zgrid,
                                                             self._R2derivGrid, kx=3,ky=3,s=0.)
            self._epifreqInterp = interpolate.InterpolatedUnivariateSpline(rs, self._epifreqGrid, k=3)

        if self._interpverticalfreq: 
            self._savedsplines['z2deriv'] = self._z2interp
            self._savedsplines['verticalfreq'] = self._verticalfreqInterp
            self._z2interp = interpolate.RectBivariateSpline(rs,
                                                             self._zgrid,
                                                             self._z2derivGrid,
                                                             kx=3,ky=3,s=0.)
            self._verticalfreqInterp = interpolate.InterpolatedUnivariateSpline(rs, self._verticalfreqGrid, k=3)


    def denormalize(self) : 
        """

        Undo the normalization.

        """
        R0 = self._normR0
        Vc0 = self._normVc0
        Phi0 = self._normPhi0
        
        # rescale the simulation
        self._s['pos'].convert_units(self._posunit)
        self._s['vel'].convert_units(self._velunit)
        
        # rescale the grid
        self._rgrid *= R0
        if self._logR: 
            self._logrgrid += np.log(R0)
            rs = self._logrgrid
        else : 
            rs = self._rgrid

        self._zgrid *= R0

        # rescale the potential 
        self._amp *= Phi0        
        
        # restore the splines
        if not self._enable_c and self._interpPot : 
            for spline,name in zip([self._potInterp, self._rforceInterp, self._zforceInterp],
                                    ["pot", "rforce", "zforce"]): 
                spline = self._savedsplines[name] 

        if self._interpPot : self._vcircInterp = self._savedsplines['vcirc']
        
        if self._interpepifreq : 
            self._R2interp = self._savedsplines['R2deriv']
            self._epifreqInterp = self._savedsplines['epifreq']

        if self._interpverticalfreq: 
            self._z2interp = self._savedsplines['z2deriv']
            self._verticalfreqInterp = self._savedsplines['verticalfreq']


      
