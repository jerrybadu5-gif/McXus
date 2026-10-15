package pg.mcxus.app

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Test
import pg.mcxus.app.chat.Media
import pg.mcxus.app.chat.Payload

class MediaTest {
    private val photo = ByteArray(150_000) { (it * 31 % 251).toByte() }

    @Test
    fun sealedFileOpensOnlyWithItsKey() {
        val sealed = Media.seal(photo)
        assertEquals(12 + photo.size + 16, sealed.ciphertext.size) // IV + data + GCM tag
        assertFalse(sealed.ciphertext.copyOfRange(12, 40).contentEquals(photo.copyOfRange(0, 28)))
        assertArrayEquals(photo, Media.open(sealed.ciphertext, sealed.key, sealed.sha256))
        val other = Media.seal(photo)
        assertNotEquals(sealed.sha256, other.sha256) // fresh key and IV every time
    }

    @Test(expected = IllegalArgumentException::class)
    fun swappedFileIsRejected() {
        val a = Media.seal(photo)
        val b = Media.seal(byteArrayOf(1, 2, 3))
        Media.open(b.ciphertext, a.key, a.sha256)
    }

    @Test(expected = javax.crypto.AEADBadTagException::class)
    fun wrongKeyFails() {
        val a = Media.seal(photo)
        Media.open(a.ciphertext, ByteArray(32), a.sha256)
    }

    @Test
    fun previews() {
        assertEquals("📷 Photo", Payload.preview(Payload.image("b", "k", "s", 10, 10, "", "")))
        assertEquals("🎤 Voice message 1:05", Payload.preview(Payload.voice("b", "k", "s", 65_400)))
        assertEquals("0:09", Payload.formatDuration(9_999))
    }
}
