#pragma once

#include <cstddef>
#include <cstring>
#include <deque>
#include <vector>

#include "FreeRTOS.h"

struct StubQueue {
    std::size_t capacity;
    std::size_t itemSize;
    std::deque<std::vector<unsigned char>> items;
};

using QueueHandle_t = StubQueue*;

inline QueueHandle_t xQueueCreate(std::size_t length, std::size_t itemSize) {
    return new StubQueue{length, itemSize, {}};
}

inline int xQueueSend(QueueHandle_t queue, const void* item, int) {
    if (!queue || queue->items.size() >= queue->capacity) {
        return pdFALSE;
    }
    std::vector<unsigned char> copy(queue->itemSize);
    std::memcpy(copy.data(), item, queue->itemSize);
    queue->items.push_back(copy);
    return pdTRUE;
}

inline int xQueueReceive(QueueHandle_t queue, void* item, int) {
    if (!queue || queue->items.empty()) {
        return pdFALSE;
    }
    const std::vector<unsigned char>& front = queue->items.front();
    std::memcpy(item, front.data(), queue->itemSize);
    queue->items.pop_front();
    return pdTRUE;
}
