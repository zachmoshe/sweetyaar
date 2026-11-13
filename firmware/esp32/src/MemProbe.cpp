#include "MemProbe.h"
#if SWEETYAAR_MEMPROBE
#include <Arduino.h>
#include <esp_debug_helpers.h>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <soc/soc_memory_layout.h>

namespace {
uint32_t g_lastFree = 0;

#if SWEETYAAR_MEMPROBE >= 2
// One entry per live block, one per distinct call chain (three return
// addresses). Sizes are stored in 4-byte units.
constexpr size_t BLOCKS = 1280;
constexpr size_t SITES = 700;
constexpr int DEPTH = 3;
struct Block { void* ptr; uint16_t units; uint16_t site; };
struct Site { uint32_t pc[DEPTH]; uint32_t liveUnits; uint16_t liveCount; uint16_t used; };
Block g_blocks[BLOCKS];
Site g_sites[SITES];
portMUX_TYPE g_mux = portMUX_INITIALIZER_UNLOCKED;
volatile bool g_tracking = false;
uint32_t g_untrackedAllocs = 0;   // table full
uint32_t g_overflowSites = 0;     // site table full: counted in the last site

uint16_t siteFor(const uint32_t* pc) {
    uint32_t hash = 2166136261u;
    for (int i = 0; i < DEPTH; ++i) hash = (hash ^ pc[i]) * 16777619u;
    size_t index = hash % (SITES - 1);
    for (size_t probe = 0; probe < SITES - 1; ++probe) {
        Site& site = g_sites[index];
        if (!site.used) {
            memcpy(site.pc, pc, sizeof(site.pc));
            site.used = 1;
            return uint16_t(index);
        }
        if (memcmp(site.pc, pc, sizeof(site.pc)) == 0) return uint16_t(index);
        index = (index + 1) % (SITES - 1);
    }
    ++g_overflowSites;
    g_sites[SITES - 1].used = 1;
    return SITES - 1;
}

void record(void* ptr, size_t size) {
    if (!ptr || !g_tracking) return;
    uint32_t pc[DEPTH] = {};
    esp_backtrace_frame_t frame = {};
    esp_backtrace_get_start(&frame.pc, &frame.sp, &frame.next_pc);
    // Skip record() and the allocator wrapper that called it.
    bool ok = esp_backtrace_get_next_frame(&frame) && esp_backtrace_get_next_frame(&frame);
    for (int i = 0; i < DEPTH && ok; ++i) {
        pc[i] = esp_cpu_process_stack_pc(frame.pc);
        ok = frame.next_pc != 0 && esp_backtrace_get_next_frame(&frame);
    }
    const uint32_t units = (size + 3) / 4;
    portENTER_CRITICAL(&g_mux);
    size_t index = (uintptr_t(ptr) >> 2) % BLOCKS;
    bool stored = false;
    for (size_t probe = 0; probe < BLOCKS; ++probe) {
        Block& block = g_blocks[index];
        if (!block.ptr || block.ptr == reinterpret_cast<void*>(1)) {
            const uint16_t site = siteFor(pc);
            block.ptr = ptr;
            block.units = units > 0xffff ? 0xffff : uint16_t(units);
            block.site = site;
            g_sites[site].liveUnits += block.units;
            ++g_sites[site].liveCount;
            stored = true;
            break;
        }
        index = (index + 1) % BLOCKS;
    }
    if (!stored) ++g_untrackedAllocs;
    portEXIT_CRITICAL(&g_mux);
}

void forget(void* ptr) {
    if (!ptr || !g_tracking) return;
    portENTER_CRITICAL(&g_mux);
    size_t index = (uintptr_t(ptr) >> 2) % BLOCKS;
    for (size_t probe = 0; probe < BLOCKS; ++probe) {
        Block& block = g_blocks[index];
        if (!block.ptr) break;  // never stored (allocated before tracking began)
        if (block.ptr == ptr) {
            g_sites[block.site].liveUnits -= block.units;
            --g_sites[block.site].liveCount;
            block.ptr = reinterpret_cast<void*>(1);  // tombstone keeps probe chains intact
            break;
        }
        index = (index + 1) % BLOCKS;
    }
    portEXIT_CRITICAL(&g_mux);
}
#endif
}  // namespace

#if SWEETYAAR_MEMPROBE >= 2
// Link-time wrappers (-Wl,--wrap=...). newlib's malloc family and the heap_caps
// family are separate entry points into the same heap; a block is recorded by
// whichever its caller used and forgotten on whichever free it reaches first.
extern "C" {
void* __real_malloc(size_t);
void* __real_calloc(size_t, size_t);
void* __real_realloc(void*, size_t);
void __real_free(void*);
void* __real_heap_caps_malloc(size_t, uint32_t);
void* __real_heap_caps_calloc(size_t, size_t, uint32_t);
void* __real_heap_caps_realloc(void*, size_t, uint32_t);
void __real_heap_caps_free(void*);

void* __wrap_malloc(size_t size) {
    void* ptr = __real_malloc(size);
    record(ptr, size);
    return ptr;
}
void* __wrap_calloc(size_t count, size_t size) {
    void* ptr = __real_calloc(count, size);
    record(ptr, count * size);
    return ptr;
}
void* __wrap_realloc(void* old, size_t size) {
    forget(old);
    void* ptr = __real_realloc(old, size);
    if (ptr) record(ptr, size);
    else if (size) record(old, heap_caps_get_allocated_size(old));
    return ptr;
}
void __wrap_free(void* ptr) {
    forget(ptr);
    __real_free(ptr);
}
void* __wrap_heap_caps_malloc(size_t size, uint32_t caps) {
    void* ptr = __real_heap_caps_malloc(size, caps);
    record(ptr, size);
    return ptr;
}
void* __wrap_heap_caps_calloc(size_t count, size_t size, uint32_t caps) {
    void* ptr = __real_heap_caps_calloc(count, size, caps);
    record(ptr, count * size);
    return ptr;
}
void* __wrap_heap_caps_realloc(void* old, size_t size, uint32_t caps) {
    forget(old);
    void* ptr = __real_heap_caps_realloc(old, size, caps);
    if (ptr) record(ptr, size);
    else if (size) record(old, heap_caps_get_allocated_size(old));
    return ptr;
}
void __wrap_heap_caps_free(void* ptr) {
    forget(ptr);
    __real_heap_caps_free(ptr);
}
}
#endif

namespace memprobe {

void begin() {
#if SWEETYAAR_MEMPROBE >= 2
    memset(g_sites, 0, sizeof(g_sites));
    g_tracking = true;
#endif
    Serial.printf("[Mem] probe level=%d\n", SWEETYAAR_MEMPROBE);
    regions();
    mark("setup-entry");
}

void mark(const char* label) {
    const uint32_t free8 = heap_caps_get_free_size(MALLOC_CAP_8BIT);
    Serial.printf("[Mem] mark %s free=%u largest=%u min=%u delta=%d\n", label,
        unsigned(free8), unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)),
        unsigned(heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT)),
        g_lastFree ? int(g_lastFree) - int(free8) : 0);
    g_lastFree = free8;
}

void regions() {
    // Every region the heap allocator was given, with its capabilities.
    struct Caps { const char* name; uint32_t caps; };
    static const Caps kinds[] = {
        {"8bit(data)", MALLOC_CAP_8BIT}, {"32bit(any)", MALLOC_CAP_32BIT},
        {"exec(iram)", MALLOC_CAP_EXEC}, {"dma", MALLOC_CAP_DMA},
        {"internal", MALLOC_CAP_INTERNAL},
    };
    for (const auto& kind : kinds) {
        multi_heap_info_t info;
        heap_caps_get_info(&info, kind.caps);
        Serial.printf("[Mem] caps %s total=%u free=%u allocated=%u largest=%u min=%u blocks=%u\n",
            kind.name, unsigned(heap_caps_get_total_size(kind.caps)),
            unsigned(info.total_free_bytes), unsigned(info.total_allocated_bytes),
            unsigned(info.largest_free_block), unsigned(info.minimum_free_bytes),
            unsigned(info.allocated_blocks));
    }
    Serial.println("[Mem] regions-begin");
    heap_caps_print_heap_info(MALLOC_CAP_32BIT);
    Serial.println("[Mem] regions-end");
}

void tasks() {
    // The prebuilt FreeRTOS has no task enumeration; look the known ones up.
    static const char* const names[] = {
        "loopTask", "main", "IDLE", "ipc0", "ipc1", "esp_timer", "Tmr Svc",
        "btController", "hciT", "BTU_TASK", "BTC_TASK", "BtA2dSinkT", "BtAppT",
        "BtI2STask", "BT_APP_TASK", "btm_rrm_t", "uart_event_task",
    };
    for (const char* name : names) {
        TaskHandle_t task = xTaskGetHandle(name);
        if (!task) continue;
        Serial.printf("[Mem] task %s stack-unused=%u\n", name,
            unsigned(uxTaskGetStackHighWaterMark(task)));
    }
}

void sites(const char* label) {
#if SWEETYAAR_MEMPROBE >= 2
    Serial.printf("[Mem] sites-begin %s untracked=%u site-overflow=%u\n", label,
        unsigned(g_untrackedAllocs), unsigned(g_overflowSites));
    for (size_t i = 0; i < SITES; ++i) {
        Site site;
        portENTER_CRITICAL(&g_mux);
        site = g_sites[i];
        portEXIT_CRITICAL(&g_mux);
        if (!site.used || !site.liveCount) continue;
        Serial.printf("[Mem] site %u %u %08x %08x %08x\n", unsigned(site.liveUnits * 4),
            unsigned(site.liveCount), unsigned(site.pc[0]), unsigned(site.pc[1]),
            unsigned(site.pc[2]));
    }
    Serial.println("[Mem] sites-end");
#else
    (void)label;
#endif
}

void poll() {
    while (Serial.available()) {
        const int c = Serial.read();
        if (c == 'm') mark("command");
        else if (c == 'r') regions();
        else if (c == 't') tasks();
        else if (c == 's') { mark("sites"); sites("command"); }
    }
}

}  // namespace memprobe
#endif
