#pragma once
#include <cstdio>

namespace openlips {
inline void startup_trace(const char* stage,long result=0)
{
#ifdef _XBOX
    char line[256];sprintf_s(line,sizeof(line),"%s: 0x%08lX\n",stage,result);
    OutputDebugStringA(line);
    FILE* file=fopen("game:\\openlips-startup.log","ab");
    if(file){fwrite(line,1,strlen(line),file);fclose(file);}
#else
    (void)stage;(void)result;
#endif
}
}
