// Play only this test file on a named CoreAudio output. Do not change the
// Mac's default output, which would also route unrelated applications.
import AVFoundation
import Foundation

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: device_tone <audio-file> <output-device-uid>\n", stderr)
    exit(2)
}
do {
    let player = try AVAudioPlayer(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    let output = CommandLine.arguments[2]
    player.currentDevice = output
    guard player.currentDevice == output, player.prepareToPlay(), player.play() else {
        throw NSError(domain: "SweetYaarDeviceTest", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "Could not play on the requested output"])
    }
    let deadline = Date().addingTimeInterval(player.duration + 5)
    while player.isPlaying && Date() < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    }
    if player.isPlaying {
        player.stop()
        throw NSError(domain: "SweetYaarDeviceTest", code: 2,
                      userInfo: [NSLocalizedDescriptionKey: "Playback timed out"])
    }
    print("Test tone completed on the requested output")
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
