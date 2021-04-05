#ifndef MKUSB_H
#define MKUSB_H

#include "windows.h"
#ifdef COMPILING_DLL
	#define DLLEXP __declspec(dllexport) 
#else
	#define DLLEXP __declspec(dllimport)
#endif


#ifdef __cplusplus
	extern "C" {
#endif


DLLEXP unsigned int __cdecl mk_version();

DLLEXP bool __cdecl mk_Init(int isMonitor, int msec);

DLLEXP void __cdecl mk_Close();

DLLEXP bool __cdecl mk_IsUpdate();

DLLEXP bool __cdecl mk_SpDevScan();

DLLEXP bool __cdecl mk_FindFirst(char* name);

DLLEXP bool __cdecl mk_FindNext(char* name);

DLLEXP bool __cdecl mk_FindClose();

DLLEXP int __cdecl mk_GetDeviceCnt();

DLLEXP int __cdecl mk_GetOptSnByName(char *name, char* sn);

DLLEXP int  __cdecl mk_OpenSpDev(char* Name);

DLLEXP int __cdecl mk_OpenSpDev_OptSn(char *sn);

DLLEXP bool __cdecl mk_CloseSpDev(int i);

DLLEXP bool __cdecl mk_Msr_Capture(int i, unsigned short isAuto, unsigned short ExpTime);

DLLEXP bool __cdecl mk_Msr_Capture_multi(int *list, bool *result, int dev_cnt, unsigned short isAuto, unsigned short ExpTime);

DLLEXP bool __cdecl mk_Msr_Dark(int i);

DLLEXP bool __cdecl mk_Msr_GetDarkStus(int i, int *stus);

DLLEXP bool __cdecl mk_Msr_Dark_multi(int *list, int dev_cnt, bool *pErr);

DLLEXP bool __cdecl mk_Msr_SetMaxExpTime(int i, unsigned int maxtime);

DLLEXP bool __cdecl mk_Msr_SetExpMode(int i, unsigned int mode);

DLLEXP bool __cdecl mk_Msr_AutoDarkCtrl(int i, unsigned int ctl);

DLLEXP bool __cdecl mk_Msr_SetCorrMatrixCH(int i, unsigned int ch);

DLLEXP bool __cdecl mk_Msr_GetCorrMatrixPara(int i, unsigned int ch, char *name, double *data);

DLLEXP bool __cdecl mk_Msr_SetCorrMatrixPara(int i, unsigned int ch, char *name, double *data);

DLLEXP bool __cdecl mk_Msr_GenerateCorrMatrix(double *ref, double *mes, int len, double *corr, int colorspace);

DLLEXP bool __cdecl mk_GetData(int i, int type, float* data);

DLLEXP bool __cdecl mk_GetSpectrum(int i, int str, int stp, float* data);

DLLEXP bool __cdecl mk_GetMicroMole(int i, int str, int stp, float *data);

DLLEXP bool __cdecl mk_GetOptSn(int i, char* sn);

DLLEXP int __cdecl mk_GetLightStrnegth(int i);

DLLEXP bool __cdecl mk_lv_GetOptSn(int i, char* sn);

DLLEXP bool __cdecl mk_lv_SetOptSn(int i, char* sn);

DLLEXP bool __cdecl mk_Peri_GetTemp(int i, float *data);

DLLEXP bool __cdecl mk_Peri_SetLCD(int i, unsigned short percent);

DLLEXP bool __cdecl mk_Peri_KeyEnable(int i);

DLLEXP bool __cdecl mk_Peri_KeyDisable(int i);

DLLEXP bool __cdecl mk_Peri_KeyClear(int i);

DLLEXP bool __cdecl mk_Peri_KeyGet(int i, unsigned int *key);

DLLEXP bool __cdecl mk_Info_Get(int i, int id, char *str_info);

DLLEXP bool __cdecl mk_flk_Dark(int i);

DLLEXP bool __cdecl mk_flk_SetPara(int i, unsigned int sample_num, unsigned int sample_freq, unsigned int fir_num, unsigned fir_cutfreq);

DLLEXP bool __cdecl mk_flk_Capture(int i, unsigned short isAutoGain, unsigned short gain, unsigned short enable_fir);

DLLEXP bool __cdecl mk_flk_GetData(int i, int type, float* data);

DLLEXP bool __cdecl mk_flk_GetTimeDomainWaveform(int i, int size, float* data);

DLLEXP bool __cdecl mk_flk_GetFreqDomainWaveform(int i, int size, float *freq, float* data);

DLLEXP bool __cdecl mk_senr_Msr_Dark(int i);

DLLEXP bool __cdecl mk_senr_Msr_Capture(int i, unsigned short isAuto, unsigned int ExpTime);

DLLEXP bool __cdecl mk_sflk_Dark(int i, unsigned int uexptime, unsigned int sampletime);

DLLEXP bool __cdecl mk_sflk_SetPara(int i, unsigned int sample_num, unsigned int sample_freq, unsigned int fir_num, unsigned fir_cutfreq);

DLLEXP bool __cdecl mk_sflk_Capture(int i, unsigned int uexptime, unsigned short enable_fir);

DLLEXP bool __cdecl mk_sflk_CaptureRaw(int i, unsigned int uexptime, void *ptr);

DLLEXP bool __cdecl mk_sflk_GetData(int i, int type, float* data);

DLLEXP bool __cdecl mk_senr_GetPeakSpRaw(int i, unsigned int exptime, unsigned int *data);

#ifdef __cplusplus
	}
#endif

#endif