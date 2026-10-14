package pg.mcxus.app

import android.content.Context
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import pg.mcxus.app.chat.ChatEngine
import pg.mcxus.app.chat.Payload
import pg.mcxus.app.chat.Readiness
import pg.mcxus.app.net.Api
import pg.mcxus.app.net.Session
import uniffi.mcxus_crypto.MlsClient
import java.io.File
import kotlin.random.Random

/**
 * Smoke test that runs ON YOUR PHONE over USB:  .\gradlew connectedDebugAndroidTest
 * Add the server to also test a real encrypted chat between two test accounts:
 *   .\gradlew connectedDebugAndroidTest "-Pandroid.testInstrumentationRunnerArguments.server=http://192.168.1.20:8000"
 */
@RunWith(AndroidJUnit4::class)
class PhoneSmokeTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    private val context: Context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun appOpens() {
        compose.waitUntil(10_000) { compose.onAllNodesWithText("McXus").fetchSemanticsNodes().isNotEmpty() }
    }

    @Test
    fun encryptionLibraryWorksOnThisPhone() {
        val dir = File(context.cacheDir, "smoke-${System.nanoTime()}").apply { mkdirs() }
        try {
            val alice = MlsClient.open(File(dir, "a.bin").path, "user:alice")
            val bob = MlsClient.open(File(dir, "b.bin").path, "user:bob")
            val gid = "smoke".toByteArray()
            bob.join(alice.createDirect(gid, bob.keyPackages(1u).single()))
            val d = bob.decrypt(gid, alice.encrypt(gid, "Moning from the phone".toByteArray()))
            assertEquals("Moning from the phone", String(d.plaintext!!))
            assertEquals(alice.safetyNumber(gid), bob.safetyNumber(gid))
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun encryptedChatThroughServer() = runBlocking {
        val server = InstrumentationRegistry.getArguments().getString("server")
        assumeTrue("pass -Pandroid.testInstrumentationRunnerArguments.server=http://<laptop-ip>:8000", !server.isNullOrBlank())
        val engines = mutableListOf<ChatEngine>()
        try {
            suspend fun phone(name: String): Pair<ChatEngine, String> {
                val session = Session(context, "smoke-$name-${System.nanoTime()}").apply { this.server = server!! }
                val api = Api(session)
                val number = "7" + Random.nextInt(1_000_000, 9_999_999)
                val code = api.post("/v1/auth/otp/request", JSONObject().put("phone", number)).getString("dev_code")
                val t = api.post("/v1/auth/otp/verify", JSONObject().put("phone", number).put("code", code))
                session.token = t.getString("access_token")
                val engine = ChatEngine.create(context, api, t.getString("user_id")).also { engines += it; it.start() }
                withTimeout(30_000) { while (!engine.online.value) delay(100) }
                return engine to t.getString("user_id")
            }
            val (kila, kilaId) = phone("kila")
            val (ruth, _) = phone("ruth")
            val conv = ruth.open(kilaId)
            assertEquals(Readiness.Ready, ruth.ensureReady(conv))
            assertTrue(ruth.send(conv, Payload.text("Smoke test hello")))
            withTimeout(40_000) {
                while (kila.messages(conv).none { Payload.parse(it.payload).optString("body") == "Smoke test hello" }) delay(200)
            }
        } finally {
            engines.forEach { it.stop() }
        }
    }
}
