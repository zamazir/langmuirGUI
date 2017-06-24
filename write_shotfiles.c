#include <ddwwansic.h>
#include <strings.h>
#include <stdio.h>
int main(int argc, char *argv[])
{
    int err=0,unit,control=3,diaref,shot=5010,ed=-1,k1=1,k2=1,i,k,t,ncal,stride=1,ind[3],length,rt,typ=2,sizes[3],adim[3],index;
    float data[182],time[223],datsig[10],adat[16];
    char exp[5],diag[4],name[9],tname[9],sgname[9],tim[19],physdim[13];
    unit = shot; 
    strcpy(exp,"AUGD"); 
    strcpy(diag,"YPR"); 
    strcpy(name,"rp");
    strcpy(tname,"time");
    strcpy(sgname,"Te");
	
/* read level-0 shotfiles to get the buffers you would like to write to level-1
    ddopen...
    time,adat,data
    ddclose... */
	
/* write level-1 shotfile */
    wwopen_ (&err,exp,diag,&shot,"new",&ed,&diaref,tim,4,3,3,18);
    if (err != 0) xxerror_ (&err,&control," ",1);
    length = 223;
    wwtbase_ (&err,&diaref,tname,&typ,&length,time,&stride,8);/* */
    if (err != 0) xxerror_ (&err,&control," ",1);
    sizes[0] = 16;
    sizes[1] = 0; 
    sizes[2] = 0;
    wwainsert_ (&err,&diaref,name,&k1,&k2,&typ,adat,sizes,8);
    if (err != 0) xxerror_ (&err,&control," ",1);
    for (k = 0; k < length; k++) { /* loop over index 2 */
        ind[0] = 1 + k;
        ind[1] = 0; 
        ind[2] = 0;
        length = 16;
        wwinsert_ (&err,&diaref,sgname,&typ,&length,data,&stride,ind,8);
        if (err != 0) xxerror_ (&err,&control," ",1);
    }
    wwclose_ (&err,&diaref,"lock","maxspace",4,8);
    if (err != 0) xxerror_ (&err,&control," ",1);
	
/* read level-1 shotfile */
    t = k2 - k1 + 1;
    ddopen_ (&err,exp,diag,&shot,&ed,&diaref,tim,4,3,18);
    if (err != 0) xxerror_ (&err,&control," ",1);
    ddainfo_ (&err,&diaref,sgname,sizes,adim,&index,8);
    if (err != 0) xxerror_ (&err,&control," ",1);
    ddagroup_ (&err,&diaref,sgname,&k1,&k2,&typ,&t,adat,&rt,8);
    if (err != 0) xxerror_ (&err,&control," ",1);
    ddcsgrp_(&err,&diaref,sgname,&k1,&k2,&typ,&length,data,&rt,&ncal,physdim,8,12);
    if (err != 0) xxerror_ (&err,&control," ",1);
    ind[0] = 1;
    ind[1] = 0;
    ind[2] = 0;
    ddcxsig_(&err,&diaref,sgname,&k1,&k2,ind,&typ,&length,data,&rt,&ncal,
             physdim,8,12);
    if (err != 0) xxerror_ (&err,&control," ",1);
    ddclose_ (&err,&diaref);
    if (err != 0) xxerror_ (&err,&control," ",1);
}