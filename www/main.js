_IMAGE_INTERVAL_MSEC = 30000;

_UUID_BATTERY_SERVICE = 0x180F;
_UUID_SWEETYAAR_SERVICE = "00000000-2504-2021-0000-000079616172";
_UUID_CURRENT_TIME_SERVICE = 0x1805

_UUID_CHAR_BATTERY_LEVEL = 0x2A19;
_UUID_CHAR_SWEETYAAR_CONTROL = "00000001-2504-2021-0000-000079616172";
_UUID_CHAR_CURRENTLY_PLAYING = "00000002-2504-2021-0000-000079616172";
_UUID_CHAR_INACTIVE_COUNTER_SEC = "00000003-2504-2021-0000-000079616172";
_UUID_CHAR_DAYTIME_MODE = "00000004-2504-2021-0000-000079616172";
_UUID_CHAR_LOG_MESSAGES = "00000005-2504-2021-0000-000079616172";
_UUID_CHAR_DATE_TIME = 0x2A08;

_SWEETYAAR_COMMANDS = {
    "play_song": 0x1,
    "play_animal": 0x2,
    "stop": 0x3,
    "kill_switch": 0x4,

    "daytime": 0x10,
    "nighttime": 0x11,
}


$(document).ready(function () {
    bluetoothModal = $("#no-bluetooth-panel");
    mainPanel = $("#remote-control-panel");
    bluetoothButton = $("#bluetooth-button");

    batteryLevelText = $("#battery-level-text");
    batteryLevelIcon = $("#battery-level-icon");
    currentlyPlayingText = $("#currently-playing-text");
    currentLocalTimeText = $("#current-local-time-text");
    inactiveCounterText = $("#inactive-counter-text");
    logMessagesUl = $("#log-messages-ul")

    buttonPlaySong = $("#button-play-song");
    buttonPlayAnimal = $("#button-play-animal");
    buttonStop = $("#button-stop");
    buttonKillSwitch = $("#button-kill-switch");
    buttonDaytime = $("#button-daytime");
    buttonNighttime = $("#button-nighttime");

    image = $("#image")

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

    batteryLevelChar = await batteryService.getCharacteristic(_UUID_CHAR_BATTERY_LEVEL);
    batteryLevelChar.addEventListener("characteristicvaluechanged", (event) => handleBatteryLevelChanged(event.target.value));
    await batteryLevelChar.startNotifications();
    handleBatteryLevelChanged(await batteryLevelChar.readValue());  // read the current value


    sweetyaarService = await server.getPrimaryService(_UUID_SWEETYAAR_SERVICE);

    currentlyPlayingChar = await sweetyaarService.getCharacteristic(_UUID_CHAR_CURRENTLY_PLAYING);
    currentlyPlayingChar.addEventListener("characteristicvaluechanged", handleCurrentlyPlayingChanged);
    await currentlyPlayingChar.startNotifications();

    sweetYaarControlChar = await sweetyaarService.getCharacteristic(_UUID_CHAR_SWEETYAAR_CONTROL);
    _setupControls(sweetYaarControlChar);

    inactiveCounterSecChar = await sweetyaarService.getCharacteristic(_UUID_CHAR_INACTIVE_COUNTER_SEC);
    inactiveCounterSecChar.addEventListener("characteristicvaluechanged", handleInactiveCounterChanged);
    await inactiveCounterSecChar.startNotifications();

    daytimeModeChar = await sweetyaarService.getCharacteristic(_UUID_CHAR_DAYTIME_MODE);
    daytimeModeChar.addEventListener("characteristicvaluechanged", (event) => handleDaytimeModeChanged(event.target.value));
    await daytimeModeChar.startNotifications();
    handleDaytimeModeChanged(await daytimeModeChar.readValue());  // read the current value

    logMessagesChar = await sweetyaarService.getCharacteristic(_UUID_CHAR_LOG_MESSAGES);
    logMessagesChar.addEventListener("characteristicvaluechanged", (event) => handleLogMessage(event.target.value));
    await logMessagesChar.startNotifications()

    currentTimeService = await server.getPrimaryService(_UUID_CURRENT_TIME_SERVICE);
    dateTimeChar = await currentTimeService.getCharacteristic(_UUID_CHAR_DATE_TIME);
    dateTimeChar.addEventListener("characteristicvaluechanged", handleDateTimeUpdate);
    await dateTimeChar.startNotifications();
    _send_current_date_time(dateTimeChar);

    bluetoothModal.hide();
    mainPanel.show();
}


function _setupControls(char) {
    buttonPlaySong.click(() => {
        sweetYaarControlChar.writeValue(new Uint8Array([_SWEETYAAR_COMMANDS["play_song"]]));
    });
    buttonPlayAnimal.click(() => {
        sweetYaarControlChar.writeValue(new Uint8Array([_SWEETYAAR_COMMANDS["play_animal"]]));
    });
    buttonStop.click(() => {
        sweetYaarControlChar.writeValue(new Uint8Array([_SWEETYAAR_COMMANDS["stop"]]));
    });
    buttonKillSwitch.click(() => {
        sweetYaarControlChar.writeValue(new Uint8Array([_SWEETYAAR_COMMANDS["kill_switch"]]));
    });
    buttonDaytime.click(() => {
        sweetYaarControlChar.writeValue(new Uint8Array([_SWEETYAAR_COMMANDS["daytime"]]));
    });
    buttonNighttime.click(() => {
        sweetYaarControlChar.writeValue(new Uint8Array([_SWEETYAAR_COMMANDS["nighttime"]]));
    });
}

function _send_current_date_time(char) {
    d = new Date();
    char.writeValue(new Uint8Array([
        d.getFullYear(), d.getFullYear() >> 8,  // Breaking the year (Uint16) to two Uint8.
        d.getMonth() + 1,
        d.getDate(),  // getDate() returns the day of month... 
        d.getHours(), d.getMinutes(), d.getSeconds()]));
}

function handleDateTimeUpdate(event) {
    values = new Uint8Array(event.target.value.buffer);
    time = new Date((values[1] << 8) + values[0], values[2] - 1, values[3], values[4], values[5], values[6])
    currentLocalTimeText.text(time.toLocaleString());
}

function handleInactiveCounterChanged(event) {
    value = new Uint16Array(event.target.value.buffer)[0];
    if (value > 0) {
        minutes = Math.floor(value / 60);
        seconds = value % 60;
        inactiveCounterText.text(minutes + ":" + (seconds < 10 ? "0" : "") + seconds);
    }
    else {
        inactiveCounterText.text("")
    }
}

// Data receiving
function handleLogMessage(value) {
    value = new TextDecoder().decode(value);
    $(logMessagesUl).append("<li>" + value + "</li>")
}

function handleBatteryLevelChanged(value) {
    value = value.getInt8();
    batteryLevelIcon.removeClass("bi-battery bi-battery-half bi-battery-full text-danger");
    batteryLevelText.removeClass("text-danger");

    batteryLevelText.text(value + "%");

    if (value < 25) {
        iconClass = "bi-battery";  // empty
        batteryLevelIcon.addClass("text-danger");
        batteryLevelText.addClass("text-danger");
    } else if (value < 75) {
        iconClass = "bi-battery-half";
    } else {
        iconClass = "bi-battery-full";
    }
    batteryLevelIcon.addClass(iconClass);
}

function handleCurrentlyPlayingChanged(event) {
    let value = new TextDecoder().decode(event.target.value);
    currentlyPlayingText.text(value);
}

function handleDaytimeModeChanged(value) {
    value = new TextDecoder().decode(value);
    daytimeI = buttonDaytime.find("i")
    nighttimeI = buttonNighttime.find("i")

    if (value == "daytime") {
        daytimeI.addClass("daytime-mode-active");
        nighttimeI.removeClass("daytime-mode-active");
    } else if (value == "nighttime") {
        daytimeI.removeClass("daytime-mode-active");
        nighttimeI.addClass("daytime-mode-active");
    } else {
        console.log("Unknown daytime mode '" + value + "'");
    }
}