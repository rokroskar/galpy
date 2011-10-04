/*
  Wrappers around the C integration code for planar Orbits
*/
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <math.h>
#include <bovy_symplecticode.h>
//Potentials
#include <galpy_potentials.h>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
/*
  Function Declarations
*/
void evalPlanarRectForce(double, double *, double *,
			 int, struct leapFuncArg *);
double calcPlanarRforce(double, double, double, 
			int, struct leapFuncArg *);
double calcPlanarphiforce(double, double, double, 
			int, struct leapFuncArg *);
/*
  Actual functions
*/
void integratePlanarOrbit(double *yo,
			  int nt, 
			  double *t,
			  int npot,
			  int * pot_type,
			  double * pot_args,
			  double rtol,
			  double atol,
			  double *result){
  //Set up the forces, first count
  int ii, jj;
  //  bool lp= (bool) logp;
  struct leapFuncArg * leapFuncArgs= (struct leapFuncArg *) malloc ( npot * sizeof (struct leapFuncArg) );
  for (ii=0; ii < npot; ii++){
    switch ( *pot_type++ ) {
    case 0: //LogarithmicHaloPotential
      leapFuncArgs->planarRforce= &LogarithmicHaloPotentialPlanarRforce;
      leapFuncArgs->planarphiforce= &ZeroPlanarForce;
      leapFuncArgs->nargs= 2;
      leapFuncArgs->args= (double *) malloc( leapFuncArgs->nargs * sizeof(double));
      for (jj=0; jj < leapFuncArgs->nargs; jj++){
	*(leapFuncArgs->args)= *pot_args++;
	leapFuncArgs->args++;
      }
      leapFuncArgs->args-= leapFuncArgs->nargs;
    }
    leapFuncArgs++;
  }
  leapFuncArgs-= npot;
  //Integrate
  leapfrog(&evalPlanarRectForce,2,yo,nt,t,npot,leapFuncArgs,rtol,atol,result);
  //Free allocated memory
  for (ii=0; ii < npot; ii++) {
    free(leapFuncArgs->args);
    leapFuncArgs++;
  }
  leapFuncArgs-= npot;
  free(leapFuncArgs);
  //Done!
}

void evalPlanarRectForce(double t, double *q, double *a,
			 int nargs, struct leapFuncArg * leapFuncArgs){
  double sinphi, cosphi, x, y, phi,R,Rforce,phiforce;
  //q is rectangular so calculate R and phi
  x= *q;
  y= *(q+1);
  //printf("%f,%f\n",x,y);
  //fflush(stdout);
  R= sqrt(x*x+y*y);
  phi= acos(x/R);
  sinphi= y/R;
  cosphi= x/R;
  if ( y < 0. ) phi= phi+2.*M_PI;
  //Calculate the forces
  Rforce= calcPlanarRforce(R,phi,t,nargs,leapFuncArgs);
  phiforce= calcPlanarphiforce(R,phi,t,nargs,leapFuncArgs);
  *a++= cosphi*Rforce-1./R*sinphi*phiforce;
  *a--= sinphi*Rforce+1./R*cosphi*phiforce;
}

double calcPlanarRforce(double R, double phi, double t, 
			int nargs, struct leapFuncArg * leapFuncArgs){
  int ii;
  double Rforce= 0.;
  for (ii=0; ii < nargs; ii++){
    Rforce+= leapFuncArgs->planarRforce(R,phi,
					leapFuncArgs->nargs,
					leapFuncArgs->args);
    leapFuncArgs++;
  }
  leapFuncArgs-= nargs;
  return Rforce;
}
double calcPlanarphiforce(double R, double phi, double t, 
			  int nargs, struct leapFuncArg * leapFuncArgs){
  int ii;
  double phiforce= 0.;
  for (ii=0; ii < nargs; ii++){
    phiforce+= leapFuncArgs->planarphiforce(R,phi,
					    leapFuncArgs->nargs,
					    leapFuncArgs->args);
    leapFuncArgs++;
  }
  leapFuncArgs-= nargs;
  return phiforce;
}
