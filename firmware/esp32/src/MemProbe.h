#pragma once
// Diagnostic RAM accounting, compiled only into the memprobe environments
// (see platformio.ini). SWEETYAAR_MEMPROBE: 0 = absent, 1 = boot checkpoints,
// 2 = checkpoints plus a live-allocation tracker (allocator calls are wrapped
// at link time and every live block is attributed to its call site).
// Output is serial only; tools/memprobe_report.py turns it into a report.
#ifndef SWEETYAAR_MEMPROBE
#define SWEETYAAR_MEMPROBE 0
#endif

#if SWEETYAAR_MEMPROBE
namespace memprobe {
void begin();                  // first line of setup()
void mark(const char* label);  // heap checkpoint
void regions();                // every heap region, all capabilities
void tasks();                  // known tasks and their stack high-water marks
void sites(const char* label); // live allocations by call site (level 2)
void poll();                   // serial commands: m=mark r=regions t=tasks s=sites
}
#define MEMPROBE_BEGIN() memprobe::begin()
#define MEMPROBE_MARK(label) memprobe::mark(label)
#define MEMPROBE_POLL() memprobe::poll()
#else
#define MEMPROBE_BEGIN() ((void)0)
#define MEMPROBE_MARK(label) ((void)0)
#define MEMPROBE_POLL() ((void)0)
#endif
