package pg.mcxus.app.util

import android.content.Context
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import java.io.File

/**
 * Voice notes: AAC in an .m4a file, mono 16 kHz at 24 kbit/s — about 30 KB for 10 seconds, clear for speech
 * and cheap on PNG mobile data. Plays on every Android 8+ phone without extra libraries.
 */
class VoiceRecorder(private val context: Context) {
    private var recorder: MediaRecorder? = null
    private var file: File? = null
    private var startedAt = 0L

    val recording: Boolean get() = recorder != null

    fun start() {
        val out = File.createTempFile("voice", ".m4a", context.cacheDir)
        val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(context) else @Suppress("DEPRECATION") MediaRecorder()
        r.setAudioSource(MediaRecorder.AudioSource.MIC)
        r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        r.setAudioChannels(1)
        r.setAudioSamplingRate(16_000)
        r.setAudioEncodingBitRate(24_000)
        r.setMaxDuration(MAX_MS.toInt())
        r.setOutputFile(out.path)
        r.prepare()
        r.start()
        recorder = r
        file = out
        startedAt = SystemClock.elapsedRealtime()
    }

    fun elapsedMs(): Long = if (recording) SystemClock.elapsedRealtime() - startedAt else 0L

    /** Stop and return the audio and its length, or null if it was too short to keep. */
    fun stop(): Pair<ByteArray, Long>? {
        val r = recorder ?: return null
        val duration = elapsedMs()
        recorder = null
        val ok = runCatching { r.stop() }.isSuccess
        r.release()
        val f = file ?: return null
        file = null
        val bytes = if (ok && duration >= MIN_MS) f.readBytes() else null
        f.delete()
        return bytes?.let { it to duration }
    }

    fun cancel() {
        recorder?.let { runCatching { it.stop() }; it.release() }
        recorder = null
        file?.delete()
        file = null
    }

    companion object {
        const val MIN_MS = 700L
        const val MAX_MS = 5 * 60_000L // 5 minutes
    }
}

/** One voice note playing at a time. */
object VoicePlayer {
    private var player: MediaPlayer? = null
    var playingPath: String? = null
        private set

    fun play(file: File, onDone: () -> Unit) {
        stop()
        player = MediaPlayer().apply {
            setDataSource(file.path)
            setOnCompletionListener { stop(); onDone() }
            prepare()
            start()
        }
        playingPath = file.path
    }

    fun positionMs(): Int = player?.currentPosition ?: 0

    fun stop() {
        player?.release()
        player = null
        playingPath = null
    }
}
