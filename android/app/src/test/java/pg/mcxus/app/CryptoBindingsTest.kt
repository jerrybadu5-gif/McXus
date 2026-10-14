package pg.mcxus.app

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import uniffi.mcxus_crypto.CryptoException
import uniffi.mcxus_crypto.MlsClient

/**
 * The generated Kotlin bindings + OpenMLS library, exactly as the app calls them (host build of the same Rust
 * code, loaded through JNA). Proves a full encrypted conversation and that state survives an app restart.
 */
class CryptoBindingsTest {
    @get:Rule val tmp = TemporaryFolder()

    @org.junit.Before
    fun needsHostLibrary() {
        val dir = java.io.File(System.getProperty("jna.library.path") ?: "")
        org.junit.Assume.assumeTrue(
            "build it first: cargo build --manifest-path crypto/Cargo.toml",
            listOf("libmcxus_crypto.so", "libmcxus_crypto.dylib", "mcxus_crypto.dll").any { dir.resolve(it).exists() },
        )
    }

    private fun client(name: String) = MlsClient.open(tmp.root.resolve("$name.bin").path, "user:$name")

    @Test
    fun twoPhonesTalkAndSurviveRestart() {
        val alice = client("alice")
        val bob = client("bob")
        val groupId = "mcxus:conv-1:abcd".toByteArray()
        val welcome = alice.createDirect(groupId, bob.keyPackages(1u).single())
        assertArrayEquals(groupId, bob.join(welcome))

        val hello = alice.encrypt(groupId, "Moning! Is the lamp available?".toByteArray())
        val got = bob.decrypt(groupId, hello)
        assertEquals("application", got.kind)
        assertEquals("user:alice", got.sender)
        assertEquals("Moning! Is the lamp available?", String(got.plaintext!!))
        assertEquals(alice.safetyNumber(groupId), bob.safetyNumber(groupId))

        // Bob's phone restarts: state is reloaded from the file and the chat continues.
        bob.destroy()
        val bobAgain = client("bob")
        assertTrue(bobAgain.hasGroup(groupId))
        val reply = bobAgain.encrypt(groupId, "Yes, K120".toByteArray())
        assertEquals("Yes, K120", String(alice.decrypt(groupId, reply).plaintext!!))
    }

    @Test
    fun strangersAndTamperingAreRejected() {
        val alice = client("a2")
        val bob = client("b2")
        val eve = client("e2")
        val gid = "g".toByteArray()
        bob.join(alice.createDirect(gid, bob.keyPackages(1u).single()))
        val secret = alice.encrypt(gid, "PIN is never sent in chat".toByteArray())
        assertFalse(eve.hasGroup(gid))
        assertThrows { eve.decrypt(gid, secret) }
        val tampered = secret.copyOf().also { it[it.size - 5] = (it[it.size - 5].toInt() xor 1).toByte() }
        assertThrows { bob.decrypt(gid, tampered) }
    }

    @Test
    fun stateFileIsBoundToItsOwner() {
        client("owner").keyPackages(1u)
        assertThrows { MlsClient.open(tmp.root.resolve("owner.bin").path, "user:someone-else") }
    }

    private fun assertThrows(block: () -> Unit) {
        try {
            block()
        } catch (e: CryptoException) {
            return
        }
        throw AssertionError("expected CryptoException")
    }
}
