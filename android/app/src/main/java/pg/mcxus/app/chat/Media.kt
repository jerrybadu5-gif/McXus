package pg.mcxus.app.chat

import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Encryption for chat photos and voice notes (the "attachment" pattern used by Signal/WhatsApp).
 *
 * Each file gets a fresh random 256-bit key and is sealed with AES-256-GCM (the phone's standard crypto
 * library, not our own algorithm). Only the ciphertext is uploaded; the key travels inside the end-to-end
 * encrypted MLS message, so the server stores bytes it cannot read. The SHA-256 of the ciphertext is also
 * in the message, so a swapped file is detected before decryption.
 */
object Media {
    private val random = SecureRandom()
    private const val IV_BYTES = 12
    private const val TAG_BITS = 128

    class Sealed(val ciphertext: ByteArray, val key: ByteArray, val sha256: String)

    fun seal(plain: ByteArray): Sealed {
        val key = ByteArray(32).also(random::nextBytes)
        val iv = ByteArray(IV_BYTES).also(random::nextBytes)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(TAG_BITS, iv))
        val out = iv + cipher.doFinal(plain)
        return Sealed(out, key, sha256(out))
    }

    /** Throws if the file was changed (wrong hash or failed GCM check). */
    fun open(ciphertext: ByteArray, key: ByteArray, expectedSha256: String): ByteArray {
        require(sha256(ciphertext) == expectedSha256) { "file does not match the message" }
        require(ciphertext.size > IV_BYTES) { "file too short" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(TAG_BITS, ciphertext, 0, IV_BYTES))
        return cipher.doFinal(ciphertext, IV_BYTES, ciphertext.size - IV_BYTES)
    }

    fun sha256(data: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }
}
