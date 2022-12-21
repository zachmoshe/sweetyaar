_IMAGE_INTERVAL_MSEC = 30000;

_UUID_BATTERY_SERVICE = 0x180F;
_UUID_SWEETYAAR_SERVICE = "10000000-2504-2021-0000-000079616172";
_UUID_CURRENT_TIME_SERVICE = 0x1805

_UUID_CHAR_BATTERY_LEVEL = 0x2A19;
_UUID_CHAR_SWEETYAAR_CONTROL = "10000001-2504-2021-0000-000079616172";
_UUID_CHAR_CURRENTLY_PLAYING = "10000002-2504-2021-0000-000079616172";
_UUID_CHAR_INACTIVE_COUNTER_SEC = "10000003-2504-2021-0000-000079616172";
_UUID_CHAR_CURRENT_PLAYLIST = "10000004-2504-2021-0000-000079616172";
_UUID_CHAR_LOG_MESSAGES = "10000005-2504-2021-0000-000079616172";
_UUID_CHAR_VOLUME = "10000006-2504-2021-0000-000079616172";
_UUID_CHAR_PLAYLISTS = "10000007-2504-2021-0000-000079616172";

_UUID_CHAR_DATE_TIME = 0x2A08;

_SWEETYAAR_COMMANDS = {
    "play_song": 1,
    "play_animal": 2,
    "stop": 3,
    "kill_switch": 4,

    "change_playlist": 10,
    "volume_up": 12,
    "volume_down": 13,

    "reset_device": 20,
}

_BUTTON_SELECTORS_TO_COMMANDS = {
    "#button-play-song": "play_song",
    "#button-play-animal": "play_animal",
    "#button-stop": "stop",
    "#button-kill-switch": "kill_switch",
    "#button-reset": "reset_device",
    "#button-volume-up": "volume_up",
    "#button-volume-down": "volume_down",
}

$(document).ready(function () {
    bluetoothModal = $("#no-bluetooth-panel");
    mainPanel = $("#remote-control-panel");
    bluetoothButton = $("#bluetooth-button");

    batteryMeter = $("#battery-meter");
    volumeMeter = $("#volume-meter");
    currentlyPlayingText = $("#currently-playing-text");
    currentLocalTimeText = $("#current-local-time-text");
    inactiveCounterText = $("#inactive-counter-text");
    logMessagesUl = $("#log-messages-ul");
    playlistsUl = $("#playlists-ul");
    playlistsButton = $("#button-current-playlist");

    image = $("#image")

    playlists = undefined;

    $.getJSON('/images/metadata.json', changeImage);
    bluetoothButton.click(connectToBluetoothDevice);
    showBluetoothModal();
});

function showBluetoothModal() {
    mainPanel.hide();
    bluetoothModal.show();
}


function changeImage(imagesData) {
    var imageUrl = imagesData[Math.floor(Math.random() * imagesData.length)];
    image.attr("src", imageUrl);

    setTimeout(changeImage, _IMAGE_INTERVAL_MSEC, imagesData);
}

async function registerCharacteristic(service, charUUID, callbackFunction) {
    char = await service.getCharacteristic(charUUID);
    char.addEventListener("characteristicvaluechanged", (event) => callbackFunction(event.target.value));
    await char.startNotifications();
    callbackFunction(await char.readValue());  // read the current value
    return char;
}

// Launch Bluetooth device chooser and connect to the selected
async function connectToBluetoothDevice() {
    device = await navigator.bluetooth.requestDevice({
        filters: [
            { services: [_UUID_BATTERY_SERVICE, _UUID_SWEETYAAR_SERVICE, _UUID_CURRENT_TIME_SERVICE] },
        ],
    });
    device.addEventListener('gattserverdisconnected', (event) => {
        bluetoothModal.show();
        mainPanel.hide();
    });
    server = await device.gatt.connect()

    batteryService = await server.getPrimaryService(_UUID_BATTERY_SERVICE);
    batteryLevelChar = await registerCharacteristic(batteryService, _UUID_CHAR_BATTERY_LEVEL, handleBatteryLevelChanged);

    sweetyaarService = await server.getPrimaryService(_UUID_SWEETYAAR_SERVICE);
    playlistsChar = await sweetyaarService.getCharacteristic(_UUID_CHAR_PLAYLISTS);
    playlists = updatePlaylists(await playlistsChar.readValue());

    currentlyPlayingChar = await registerCharacteristic(sweetyaarService, _UUID_CHAR_CURRENTLY_PLAYING, handleCurrentlyPlayingChanged);
    inactiveCounterSecChar = await registerCharacteristic(sweetyaarService, _UUID_CHAR_INACTIVE_COUNTER_SEC, handleInactiveCounterChanged);
    currentPlaylistChar = await registerCharacteristic(sweetyaarService, _UUID_CHAR_CURRENT_PLAYLIST, handleCurrentPlaylistChanged);
    logMessagesChar = await registerCharacteristic(sweetyaarService, _UUID_CHAR_LOG_MESSAGES, handleLogMessage);
    volumeChar = await registerCharacteristic(sweetyaarService, _UUID_CHAR_VOLUME, handleVolumeChanged);
    sweetYaarControlChar = await sweetyaarService.getCharacteristic(_UUID_CHAR_SWEETYAAR_CONTROL);
    setupControls(sweetYaarControlChar);

    currentTimeService = await server.getPrimaryService(_UUID_CURRENT_TIME_SERVICE);
    dateTimeChar = await registerCharacteristic(currentTimeService, _UUID_CHAR_DATE_TIME, handleDateTimeUpdate);
    sendCurrentDateTime(dateTimeChar);

    bluetoothModal.hide();
    mainPanel.show();
}


function setupControls(char) {
    for (const [buttonSelector, command] of Object.entries(_BUTTON_SELECTORS_TO_COMMANDS)) {
        button = $(buttonSelector);
        button.click(() => {
            char.writeValue(new Uint8Array([_SWEETYAAR_COMMANDS[command]]));
        });
    }
}

function sendCurrentDateTime(char) {
    d = new Date();
    char.writeValue(new Uint8Array([
        d.getFullYear(), d.getFullYear() >> 8,  // Breaking the year (Uint16) to two Uint8.
        d.getMonth() + 1,
        d.getDate(),  // getDate() returns the day of month... 
        d.getHours(), d.getMinutes(), d.getSeconds()]));
}

function handleDateTimeUpdate(value) {
    values = new Uint8Array(value.buffer);
    time = new Date((values[1] << 8) + values[0], values[2] - 1, values[3], values[4], values[5], values[6])
    currentLocalTimeText.text(time.toLocaleString());
}

function handleInactiveCounterChanged(value) {
    if (value.byteLength == 0) return;
    value = value.getUint16(0, littleEndian = true)
    if (value > 0) {
        minutes = Math.floor(value / 60);
        seconds = value % 60;
        inactiveCounterText.text(minutes + ":" + (seconds < 10 ? "0" : "") + seconds);
    }
    else {
        inactiveCounterText.text("")
    }
}

function handleLogMessage(value) {
    value = new TextDecoder().decode(value);
    $(logMessagesUl).append("<li>" + value + "</li>")
}

function handleBatteryLevelChanged(value) {
    value = value.getInt8();
    $(batteryMeter).width(value + "%");
    color = (value < 25 ? "crimson" : value < 75 ? "orange" : "limegreen");  // crimson is red, 
    $(batteryMeter).css("background-color", color);
}

function handleCurrentlyPlayingChanged(value) {
    value = new TextDecoder().decode(value);
    currentlyPlayingText.text(value);
}

function handleCurrentPlaylistChanged(value) {
    playlistName = new TextDecoder().decode(value);
    playlistReprName = playlists[playlistName];
    playlistsButton.text(playlistReprName);
}

function handleVolumeChanged(value) {
    value = value.getInt8();
    $(volumeMeter).height(value + "%");
    color = (value < 25 ? "crimson" : value < 75 ? "orange" : "limegreen");  // crimson is red, 
    $(volumeMeter).css("background-color", color);
}

function updatePlaylists(value) {
    value = new TextDecoder().decode(value);
    if (value == "") return;

    playlists = JSON.parse(value)

    playlistsUl.empty();
    for ([playlistName, playlistReprName] of Object.entries(playlists)) {
        playlist_li = jQuery('<li playlist="' + playlistName + '"><a class="dropdown-item" href="#">' + playlistReprName + '</a></li>')
        playlist_li.click((e) => {
            playlistName = $(e.currentTarget).attr("playlist");
            currentPlaylistChar.writeValue(new TextEncoder().encode(playlistName));
        });
        playlistsUl.prepend(playlist_li);
    }
    return playlists;
}