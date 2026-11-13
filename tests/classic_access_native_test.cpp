#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <set>
#include "recording_serial.h"
#include "DevLog.h"
#define ESP_IDF_VERSION_VAL(a, b, c) ((a) * 10000 + (b) * 100 + (c))
#define ESP_IDF_VERSION ESP_IDF_VERSION_VAL(4, 4, 7)
#define CONFIG_BTDM_CTRL_BR_EDR_MAX_ACL_CONN 2
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(mux) ((void)(mux))
#define portEXIT_CRITICAL(mux) ((void)(mux))
uint32_t fakeNow = 1234;
uint32_t millis() { return fakeNow; }

using esp_bt_gap_cb_event_t = int;
using esp_bt_discovery_mode_t = int;
using esp_bt_pin_code_t = uint8_t[16];
using esp_bd_addr_t = uint8_t[6];
constexpr int ESP_BT_STATUS_HCI_SUCCESS = 0x100;
enum { ESP_BT_NON_CONNECTABLE, ESP_BT_CONNECTABLE, ESP_BT_NON_DISCOVERABLE,
    ESP_BT_GENERAL_DISCOVERABLE, ESP_BT_GAP_CFM_REQ_EVT, ESP_BT_GAP_PIN_REQ_EVT,
    ESP_BT_GAP_KEY_REQ_EVT, ESP_BT_GAP_KEY_NOTIF_EVT, ESP_BT_GAP_AUTH_CMPL_EVT,
    ESP_BT_STATUS_SUCCESS, ESP_A2D_CONNECTION_STATE_CONNECTED,
    ESP_A2D_CONNECTION_STATE_DISCONNECTED, ESP_A2D_CONNECTION_STATE_CONNECTING,
    ESP_A2D_CONNECTION_STATE_DISCONNECTING, ESP_BT_GAP_ACL_CONN_CMPL_STAT_EVT,
    ESP_BT_GAP_ACL_DISCONN_CMPL_STAT_EVT };
struct esp_bt_gap_cb_param_t {
    struct { uint8_t bda[6] = {}; } cfm_req, pin_req, key_req;
    struct { uint8_t bda[6] = {}; int stat = ESP_BT_STATUS_SUCCESS; } auth_cmpl;
    struct { uint8_t bda[6] = {}; int stat = ESP_BT_STATUS_HCI_SUCCESS; } acl_conn_cmpl_stat;
    struct { uint8_t bda[6] = {}; int reason = 0; } acl_disconn_cmpl_stat;
};
struct esp_a2d_cb_param_t {
    struct { int state = 0, disc_rsn = 0; uint8_t remote_bda[6] = {}; } conn_stat;
};
int connectable = -1, discoverable = -1, rejected = 0;
int lastDisconnected = -1;
bool confirmed = false;
int pairable = -1;
std::set<uint8_t> removed;
int esp_bt_gap_set_scan_mode(int connection, int discovery) { connectable = connection; discoverable = discovery; return 0; }
extern "C" void __wrap_BTA_DmConfirm(uint8_t*, uint8_t);
extern "C" void __real_BTA_DmConfirm(uint8_t*, uint8_t allow) { confirmed = allow; }
extern "C" void BTA_DmSetVisibility(uint16_t disc, uint16_t conn, uint8_t pairing, uint8_t filter) {
    assert((disc & 0xff00) == 0xff00 && (conn & 0xff00) == 0xff00);
    assert(filter == 0); // Just Works keys must not be excluded by the MITM filter.
    connectable = (conn & 0xff) ? ESP_BT_CONNECTABLE : ESP_BT_NON_CONNECTABLE;
    discoverable = (disc & 0xff) ? ESP_BT_GENERAL_DISCOVERABLE : ESP_BT_NON_DISCOVERABLE;
    pairable = pairing;
}
int esp_bt_gap_ssp_confirm_reply(uint8_t* address, bool allow) { __wrap_BTA_DmConfirm(address, allow); return 0; }
int esp_bt_gap_pin_reply(uint8_t*, bool allow, int, uint8_t*) { assert(!allow); return 0; }
int esp_bt_gap_ssp_passkey_reply(uint8_t*, bool allow, int) { assert(!allow); return 0; }
void esp_bt_gap_remove_bond_device(uint8_t* address) { removed.insert(address[5]); }
std::set<uint8_t> closed;  // links closed with their bond kept
extern "C" void BTA_DmCloseACL(uint8_t* address, uint8_t removeBond, uint8_t transport) {
    assert(!removeBond && transport == 1);  // BR/EDR, and never deletes keys
    closed.insert(address[5]);
}
void esp_a2d_sink_disconnect(uint8_t* address) { ++rejected; lastDisconnected = address[5]; }
struct BluetoothAccess {
    bool open = false;
    bool available = true;
    std::set<uint8_t> bonds;
    bool ready() { return available; }
    bool pairingOpen() { return available && open; }
    bool classicConnectionsAllowed() { return available && (open || !bonds.empty()); }
    bool classicBonded(const uint8_t* address) { return available && bonds.count(address[5]); }
} bluetoothAccess;
namespace ClassicBluetooth {}
#include "classic_adapter_under_test.inc"
class LowLatencyA2DPSinkQueued {
public:
    bool connected = false, audio = false;
    esp_bd_addr_t currentPeer{};
    int connectionEvents = 0, audioEvents = 0;
    bool is_connected() { return connected; }
    esp_bd_addr_t* get_current_peer_address() { return &currentPeer; }
    void set_i2s_active(bool on) { audio = on; }
    void disconnect() { connected = false; }
    virtual void set_scan_mode_connectable(bool) {}
    virtual void set_discoverability(int) {}
    virtual void app_gap_callback(int, esp_bt_gap_cb_param_t*) {}
    virtual void handle_connection_state(uint16_t, void* data) {
        ++connectionEvents;
        connected = static_cast<esp_a2d_cb_param_t*>(data)->conn_stat.state == ESP_A2D_CONNECTION_STATE_CONNECTED;
        memcpy(currentPeer, static_cast<esp_a2d_cb_param_t*>(data)->conn_stat.remote_bda, 6);
    }
    virtual void handle_audio_state(uint16_t, void*) { ++audioEvents; audio = true; }
    virtual size_t write_audio(const uint8_t*, size_t size) { return size; }
};
#include "classic_access_under_test.inc"
class TestSink : public ApprovedA2DPSink {
public:
    using ApprovedA2DPSink::app_gap_callback;
    using ApprovedA2DPSink::handle_connection_state;
    using ApprovedA2DPSink::handle_audio_state;
    using ApprovedA2DPSink::write_audio;
    using ApprovedA2DPSink::set_scan_mode_connectable;
};
int main() {
    TestSink sink;
    auto link = [&](uint8_t id, bool connect = true) {
        esp_bt_gap_cb_param_t event{};
        event.acl_conn_cmpl_stat.bda[5] = id;
        event.acl_disconn_cmpl_stat.bda[5] = id;
        sink.app_gap_callback(connect ? ESP_BT_GAP_ACL_CONN_CMPL_STAT_EVT : ESP_BT_GAP_ACL_DISCONN_CMPL_STAT_EVT, &event);
    };
    sink.refreshAccess();
    assert(connectable == ESP_BT_NON_CONNECTABLE && discoverable == ESP_BT_NON_DISCOVERABLE);
    esp_bt_gap_cb_param_t gap{};
    sink.app_gap_callback(ESP_BT_GAP_CFM_REQ_EVT, &gap);
    assert(!confirmed);
    assert(Serial.output.find("PAIRING_REQUEST") != std::string::npos);
    assert(Serial.output.find("decision=deny-window-closed") != std::string::npos);
    gap.auth_cmpl.bda[5] = 1;
    sink.app_gap_callback(ESP_BT_GAP_AUTH_CMPL_EVT, &gap);
    assert(removed.count(1) && bluetoothAccess.bonds.empty());
    esp_a2d_cb_param_t connection{};
    connection.conn_stat.state = ESP_A2D_CONNECTION_STATE_CONNECTED;
    connection.conn_stat.remote_bda[5] = 1;
    sink.handle_connection_state(0, &connection);
    sink.handle_audio_state(0, nullptr);
    assert(sink.connectionEvents == 0 && sink.audioEvents == 0 && sink.write_audio(nullptr, 100) == 0);
    link(0, false); // rejected code-confirm test above

    bluetoothAccess.open = true;
    sink.refreshAccess();
    assert(connectable == ESP_BT_CONNECTABLE && discoverable == ESP_BT_GENERAL_DISCOVERABLE);
    gap.cfm_req.bda[5] = 1;
    link(1);
    // SDK Just Works path: directly calls BTA_DmConfirm, no public CFM event.
    __wrap_BTA_DmConfirm(gap.cfm_req.bda, true);
    assert(confirmed);
    bluetoothAccess.bonds.insert(1); // SDK saves the key before AUTH_CMPL
    sink.app_gap_callback(ESP_BT_GAP_AUTH_CMPL_EVT, &gap);
    sink.handle_connection_state(0, &connection);
    sink.handle_audio_state(0, nullptr);
    assert(sink.connected && sink.audioEvents == 1 && sink.write_audio(nullptr, 100) == 100);
    sink.refreshAccess();
    assert(sink.connected && connectable == ESP_BT_NON_CONNECTABLE); // opening pairing keeps current audio
    assert(bluetoothAccess.open); // connection does not close enrollment

    bluetoothAccess.open = false;
    connection.conn_stat.state = ESP_A2D_CONNECTION_STATE_DISCONNECTED;
    sink.handle_connection_state(0, &connection);
    sink.set_scan_mode_connectable(true); // library's automatic reconnect path
    assert(connectable == ESP_BT_CONNECTABLE && discoverable == ESP_BT_NON_DISCOVERABLE);
    link(1, false); link(1);
    __wrap_BTA_DmConfirm(gap.cfm_req.bda, true);
    assert(!confirmed); // even a known address cannot create new keys outside the window
    assert(!ClassicBluetooth::canUseAudio(gap.cfm_req.bda));
    link(1, false); link(1); // saved-key reconnect has no confirmation event
    connection.conn_stat.state = ESP_A2D_CONNECTION_STATE_CONNECTED;
    sink.handle_connection_state(0, &connection);
    assert(sink.connected && sink.write_audio(nullptr, 100) == 100); // remembered source
    bluetoothAccess.available = false;
    sink.revokeSession();
    assert(lastDisconnected == 1 && !sink.audio && sink.write_audio(nullptr, 100) == 0);
    connection.conn_stat.state = ESP_A2D_CONNECTION_STATE_DISCONNECTED;
    sink.handle_connection_state(0, &connection); // radio disconnect is asynchronous
    assert(!sink.connected);
    assert(connectable == ESP_BT_NON_CONNECTABLE);
    assert(ClassicBluetooth::hasLinks()); // deletion/reset must wait for real disconnect
    link(1, false);
    assert(!ClassicBluetooth::hasLinks());
    bluetoothAccess.bonds.clear();
    bluetoothAccess.available = true;
    gap.auth_cmpl.stat = 5;
    sink.app_gap_callback(ESP_BT_GAP_AUTH_CMPL_EVT, &gap);
    assert(Serial.output.find("AUTH_COMPLETE peer=00:00:00:00:00:01 code=0x05 pairing=closed decision=stack-authentication-failed") != std::string::npos);
    gap.acl_conn_cmpl_stat.bda[5] = 2;
    sink.app_gap_callback(ESP_BT_GAP_ACL_CONN_CMPL_STAT_EVT, &gap);
    assert(Serial.output.find("ACL_CONNECT peer=00:00:00:00:00:02") != std::string::npos);
    gap.acl_disconn_cmpl_stat.reason = 0x13;
    sink.app_gap_callback(ESP_BT_GAP_ACL_DISCONN_CMPL_STAT_EVT, &gap);
    assert(Serial.output.find("ACL_DISCONNECT peer=00:00:00:00:00:00 code=0x13") != std::string::npos);
    link(2, false);

    // A pairing admitted near the deadline cannot become an authorized audio
    // session after timeout, even if bond deletion is still asynchronous.
    bluetoothAccess.open = true;
    gap.cfm_req.bda[5] = 2;
    link(2);
    __wrap_BTA_DmConfirm(gap.cfm_req.bda, true);
    assert(confirmed);
    bluetoothAccess.bonds.insert(2);
    assert(!ClassicBluetooth::canUseAudio(gap.cfm_req.bda)); // not yet authenticated
    bluetoothAccess.open = false;
    gap.auth_cmpl.bda[5] = 2;
    gap.auth_cmpl.stat = ESP_BT_STATUS_SUCCESS;
    sink.app_gap_callback(ESP_BT_GAP_AUTH_CMPL_EVT, &gap);
    assert(removed.count(2) && !ClassicBluetooth::canUseAudio(gap.cfm_req.bda));
    link(2, false);

    // Same-address impersonation cannot use an old entry after failed key auth.
    link(2);
    assert(!ClassicBluetooth::authenticated(gap.cfm_req.bda, false));
    assert(!ClassicBluetooth::canUseAudio(gap.cfm_req.bda));
    link(2, false);

    // Closing a link never costs a saved bond. A third link has no slot (the
    // controller allows two) and is closed with its bond kept.
    removed.clear(); closed.clear();
    bluetoothAccess.bonds = {3, 4, 5};
    link(3); link(4); link(5);
    assert(closed.count(5) && removed.empty());
    link(4, false);
    // A bonded phone refused on a rejected link keeps its bond too.
    closed.clear();
    link(5);
    gap.auth_cmpl.bda[5] = 5;
    gap.auth_cmpl.stat = ESP_BT_STATUS_SUCCESS;
    ClassicBluetooth::disconnectAll();          // marks every link rejected
    removed.clear();
    sink.app_gap_callback(ESP_BT_GAP_AUTH_CMPL_EVT, &gap);
    assert(closed.count(5) && !removed.count(5));
    // An A2DP connection that is not approved closes the whole link, so the
    // phone does not stay "connected" to a toy that is not its speaker.
    closed.clear();
    connection.conn_stat.state = ESP_A2D_CONNECTION_STATE_CONNECTED;
    connection.conn_stat.remote_bda[5] = 5;
    sink.handle_connection_state(0, &connection);
    assert(closed.count(5) && !removed.count(5));
    link(5, false); link(3, false);
    // A link with no A2DP connection is closed after IDLE_LINK_MS; one with
    // audio, or one still pairing inside the window, is left alone.
    closed.clear(); removed.clear();
    link(3); link(4);
    uint8_t three[6] = {0, 0, 0, 0, 0, 3}, four[6] = {0, 0, 0, 0, 0, 4};
    ClassicBluetooth::audioConnected(three, true);
    assert(ClassicBluetooth::closeIdleLinks(millis() + ClassicBluetooth::IDLE_LINK_MS - 1) == 0);
    assert(ClassicBluetooth::closeIdleLinks(millis() + ClassicBluetooth::IDLE_LINK_MS) == 1);
    assert(closed.count(4) && !closed.count(3) && removed.empty());
    assert(ClassicBluetooth::closeIdleLinks(millis() + 2 * ClassicBluetooth::IDLE_LINK_MS) == 0); // once
    link(4, false);
    ClassicBluetooth::audioConnected(three, false);
    bluetoothAccess.open = true;
    esp_bt_gap_ssp_confirm_reply(three, true);  // pairing in progress
    assert(ClassicBluetooth::pairedOnThisLink(three) && !ClassicBluetooth::pairedOnThisLink(four));
    assert(ClassicBluetooth::closeIdleLinks(millis() + 2 * ClassicBluetooth::IDLE_LINK_MS) == 0);
    bluetoothAccess.open = false;
    assert(ClassicBluetooth::closeIdleLinks(millis() + 2 * ClassicBluetooth::IDLE_LINK_MS) == 1);
    link(3, false);
    // A paired phone whose link ends without ever getting A2DP, though nothing
    // here refused or closed it, is reported once so the firmware can restart.
    bluetoothAccess.bonds = {3, 4, 5};
    bluetoothAccess.open = false;
    (void)ClassicBluetooth::takeIncompleteLink();
    link(3); fakeNow += ClassicBluetooth::INCOMPLETE_LINK_MS - 1; link(3, false);
    assert(!ClassicBluetooth::takeIncompleteLink());            // too short to judge
    link(3); fakeNow += ClassicBluetooth::INCOMPLETE_LINK_MS; link(3, false);
    assert(ClassicBluetooth::takeIncompleteLink() && !ClassicBluetooth::takeIncompleteLink());
    link(3); ClassicBluetooth::audioConnected(three, true); ClassicBluetooth::audioConnected(three, false);
    fakeNow += ClassicBluetooth::INCOMPLETE_LINK_MS; link(3, false);
    assert(!ClassicBluetooth::takeIncompleteLink());            // it did get its audio
    link(3); fakeNow += ClassicBluetooth::IDLE_LINK_MS;
    assert(ClassicBluetooth::closeIdleLinks(millis()) == 1);
    link(3, false);
    assert(!ClassicBluetooth::takeIncompleteLink());            // closed by the toy itself
    // A new phone pairing, and a phone the toy has forgotten, also leave
    // without audio; neither is a sign of trouble.
    bluetoothAccess.open = true;
    link(3);
    esp_bt_gap_ssp_confirm_reply(three, true);
    fakeNow += ClassicBluetooth::INCOMPLETE_LINK_MS; link(3, false);
    assert(!ClassicBluetooth::takeIncompleteLink());
    bluetoothAccess.open = false;
    (void)ClassicBluetooth::takePairingRefused();
    link(9);                                                    // not among the saved pairings
    assert(ClassicBluetooth::takePairingRefused());             // the toy signals the refusal
    fakeNow += ClassicBluetooth::INCOMPLETE_LINK_MS; link(9, false);
    assert(!ClassicBluetooth::takeIncompleteLink());
    // A pairing request while pairing mode is closed is reported once, so
    // the toy can signal the refusal; one inside the window is not.
    (void)ClassicBluetooth::takePairingRefused();
    bluetoothAccess.open = false;
    link(3);
    esp_bt_gap_ssp_confirm_reply(three, true);
    assert(ClassicBluetooth::takePairingRefused() && !ClassicBluetooth::takePairingRefused());
    link(3, false);
    bluetoothAccess.open = true;
    link(3);
    esp_bt_gap_ssp_confirm_reply(three, true);
    assert(!ClassicBluetooth::takePairingRefused());
    link(3, false);
    bluetoothAccess.open = false;
    std::cout << "Classic authorization tests passed\n";
}
