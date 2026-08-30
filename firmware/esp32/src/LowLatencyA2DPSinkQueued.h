#pragma once

#include <Arduino.h>
#include <esp_heap_caps.h>

#include "BluetoothA2DPSinkQueued.h"

class LowLatencyA2DPSinkQueued : public BluetoothA2DPSinkQueued {
public:
    using BluetoothA2DPSinkQueued::BluetoothA2DPSinkQueued;

    bool reserveAudioQueue() {
        return ensureI2SResources(false);
    }

    bool reserveAudioTask() {
        return ensureI2SResources(true);
    }

    void printStats(const char* tag = "BT") {
        UBaseType_t bytesWaiting = 0;
        if (s_ringbuf_i2s != nullptr) {
            vRingbufferGetInfo(s_ringbuf_i2s, nullptr, nullptr, nullptr, nullptr, &bytesWaiting);
        }

        Serial.printf("[%s] Stats rb=%u/%dB rx=%luB tx=%luB underflows=%lu drops=%lu mode=%d active=%d\n",
                      tag,
                      static_cast<unsigned>(bytesWaiting), i2s_ringbuffer_size,
                      static_cast<unsigned long>(rxBytes),
                      static_cast<unsigned long>(txBytes),
                      static_cast<unsigned long>(underflows),
                      static_cast<unsigned long>(drops),
                      static_cast<int>(ringbuffer_mode),
                      is_i2s_active ? 1 : 0);
    }

protected:
    void set_i2s_active(bool active) override {
        is_i2s_active = active;
        if (active) {
            ringbuffer_mode = RINGBUFFER_MODE_PREFETCHING;
            is_starting = true;
        }
    }

    void bt_i2s_task_start_up(void) override {
        ensureI2SResources(true);
    }

    void bt_i2s_task_shut_down(void) override {
        is_i2s_active = false;
        ringbuffer_mode = RINGBUFFER_MODE_PREFETCHING;
        is_starting = true;
        drainAudioQueue();
    }

    void i2s_task_handler(void*) override {
        is_starting = true;
        while (true) {
            if (s_ringbuf_i2s == nullptr || s_i2s_write_semaphore == nullptr) {
                delay(20);
                continue;
            }

            if (is_starting) {
                if (pdTRUE != xSemaphoreTake(s_i2s_write_semaphore, portMAX_DELAY)) {
                    continue;
                }
                is_starting = false;
            }

            size_t item_size = 0;
            auto* data = static_cast<uint8_t*>(
                xRingbufferReceiveUpTo(
                    s_ringbuf_i2s, &item_size, (TickType_t)pdMS_TO_TICKS(i2s_ticks),
                    i2s_write_size_upto));
            if (item_size == 0 || data == nullptr) {
                if (is_i2s_active && ringbuffer_mode != RINGBUFFER_MODE_PREFETCHING) {
                    underflows++;
                    ringbuffer_mode = RINGBUFFER_MODE_PREFETCHING;
                }
                continue;
            }

            if (is_i2s_active && is_output) {
                txBytes += i2s_write_data(data, item_size);
            }

            vRingbufferReturnItem(s_ringbuf_i2s, static_cast<void*>(data));
            taskYIELD();
        }
    }

    size_t write_audio(const uint8_t* data, size_t size) override {
        rxBytes += size;
        if (s_ringbuf_i2s == nullptr || s_i2s_write_semaphore == nullptr) {
            drops++;
            return 0;
        }

        size_t accepted = BluetoothA2DPSinkQueued::write_audio(data, size);
        if (accepted == 0 && is_i2s_active) {
            drops++;
        }
        return accepted;
    }

    void handle_audio_state(uint16_t, void* pParam) override {
        auto* a2d = static_cast<esp_a2d_cb_param_t*>(pParam);
        audio_state = a2d->audio_stat.state;

        if (audio_state_callback != nullptr) {
            audio_state_callback(audio_state, audio_state_obj);
        }

        if (!is_encoded_output()) {
            if (audio_state == ESP_A2D_AUDIO_STATE_STARTED) {
                set_i2s_active(true);
            } else if (audio_state == ESP_A2D_AUDIO_STATE_STOPPED) {
                set_i2s_active(false);
                drainAudioQueue();
            } else if (audio_state == ESP_A2D_AUDIO_STATE_REMOTE_SUSPEND) {
                ringbuffer_mode = RINGBUFFER_MODE_PREFETCHING;
                is_starting = true;
            }
        }

        if (audio_state_callback_post != nullptr) {
            audio_state_callback_post(audio_state, audio_state_obj_post);
        }
    }

private:
    volatile uint32_t rxBytes = 0;
    volatile uint32_t txBytes = 0;
    volatile uint32_t underflows = 0;
    volatile uint32_t drops = 0;

    void drainAudioQueue() {
        if (s_ringbuf_i2s == nullptr) {
            return;
        }

        while (true) {
            size_t itemSize = 0;
            void* item = xRingbufferReceiveUpTo(s_ringbuf_i2s, &itemSize, 0, i2s_write_size_upto);
            if (item == nullptr || itemSize == 0) {
                break;
            }
            vRingbufferReturnItem(s_ringbuf_i2s, item);
        }
    }

    bool ensureI2SResources(bool startTask) {
        ringbuffer_mode = RINGBUFFER_MODE_PREFETCHING;

        if (s_i2s_write_semaphore == nullptr) {
            s_i2s_write_semaphore = xSemaphoreCreateBinary();
            if (s_i2s_write_semaphore == nullptr) {
                Serial.printf("[BT] A2DP semaphore allocation failed (free=%u largest=%u)\n",
                              heap_caps_get_free_size(MALLOC_CAP_8BIT),
                              heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
                return false;
            }
        }

        if (s_ringbuf_i2s == nullptr) {
            int requestedSize = i2s_ringbuffer_size;
            const int sizes[] = {
                requestedSize,
                24 * 1024,
                16 * 1024,
                12 * 1024,
                8 * 1024,
            };

            for (size_t i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
                int size = sizes[i];
                if (size <= 0 || size > requestedSize) {
                    continue;
                }

                bool alreadyTried = false;
                for (size_t j = 0; j < i; j++) {
                    if (sizes[j] == size) {
                        alreadyTried = true;
                        break;
                    }
                }
                if (alreadyTried) {
                    continue;
                }

                s_ringbuf_i2s = xRingbufferCreate(size, RINGBUF_TYPE_BYTEBUF);
                if (s_ringbuf_i2s != nullptr) {
                    if (size != requestedSize) {
                        Serial.printf("[BT] A2DP queue fell back to %dB (requested %dB, free=%u largest=%u)\n",
                                      size, requestedSize,
                                      heap_caps_get_free_size(MALLOC_CAP_8BIT),
                                      heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
                    } else {
                        Serial.printf("[BT] A2DP queue ready: %dB (free=%u largest=%u)\n",
                                      size,
                                      heap_caps_get_free_size(MALLOC_CAP_8BIT),
                                      heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
                    }
                    i2s_ringbuffer_size = size;
                    break;
                }
            }

            if (s_ringbuf_i2s == nullptr) {
                Serial.printf("[BT] A2DP ringbuffer allocation failed (requested %dB, free=%u largest=%u)\n",
                              requestedSize,
                              heap_caps_get_free_size(MALLOC_CAP_8BIT),
                              heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
                return false;
            }
        }

        if (!startTask) {
            return true;
        }

        drainAudioQueue();

        if (s_bt_i2s_task_handle == nullptr) {
            BaseType_t result = xTaskCreatePinnedToCore(
                ccall_i2s_task_handler, "BtI2STask", i2s_stack_size, nullptr,
                i2s_task_priority, &s_bt_i2s_task_handle, task_core);
            if (result != pdPASS) {
                Serial.printf("[BT] A2DP I2S task allocation failed (free=%u largest=%u)\n",
                              heap_caps_get_free_size(MALLOC_CAP_8BIT),
                              heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
                return false;
            }
        }

        return true;
    }
};
