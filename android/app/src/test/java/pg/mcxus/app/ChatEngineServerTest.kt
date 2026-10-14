package pg.mcxus.app

import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import pg.mcxus.app.chat.ChatEngine
import pg.mcxus.app.chat.Payload
import pg.mcxus.app.chat.Readiness
import pg.mcxus.app.net.Api
import pg.mcxus.app.net.Session
import kotlin.random.Random

/**
 * Two phones (two ChatEngines, the real app code) chatting through a running McXus server.
 * Runs only when MCXUS_E2E_SERVER is set, e.g.  MCXUS_E2E_SERVER=http://127.0.0.1:8000 ./gradlew testDebugUnitTest
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ChatEngineServerTest {
    private val server: String? = System.getenv("MCXUS_E2E_SERVER")
    private val engines = mutableListOf<ChatEngine>()

    private class Phone(val engine: ChatEngine, val userId: String)

    @Before
    fun needsServer() = assumeTrue("set MCXUS_E2E_SERVER to run", !server.isNullOrBlank())

    @After
    fun stop() = engines.forEach { it.stop() }

    private suspend fun phone(name: String): Phone {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val session = Session(context, "test-$name").apply { this.server = this@ChatEngineServerTest.server!! }
        val api = Api(session)
        val number = "7" + Random.nextInt(1_000_000, 9_999_999)
        val code = api.post("/v1/auth/otp/request", JSONObject().put("phone", number)).getString("dev_code")
        val token = api.post("/v1/auth/otp/verify", JSONObject().put("phone", number).put("code", code))
        session.token = token.getString("access_token")
        val userId = token.getString("user_id")
        val engine = ChatEngine.create(context, api, userId).also { engines += it; it.start() }
        withTimeout(30_000) { while (!engine.online.value) delay(100) } // device registered, keys uploaded
        return Phone(engine, userId)
    }

    private suspend fun waitFor(phone: Phone, conv: String, body: String) = withTimeout(40_000) {
        while (phone.engine.messages(conv).none { Payload.parse(it.payload).optString("body") == body }) delay(200)
    }

    @Test
    fun encryptedChatBothWays() = runBlocking {
        val kila = phone("kila")
        val ruth = phone("ruth")

        val conv = ruth.engine.open(kila.userId)
        assertEquals(Readiness.Ready, ruth.engine.ensureReady(conv))
        assertEquals(true, ruth.engine.send(conv, Payload.text("Moning! Is the solar lamp still available?")))

        waitFor(kila, conv, "Moning! Is the solar lamp still available?")
        assertEquals(1, kila.engine.conversations.value.single { it.id == conv }.unread)
        assertEquals(Readiness.Ready, kila.engine.ensureReady(conv)) // joined from the Welcome
        kila.engine.send(conv, Payload.text("Yes, K120 with phone charger."))
        waitFor(ruth, conv, "Yes, K120 with phone charger.")

        kila.engine.markRead(conv)
        assertEquals(0, kila.engine.conversations.value.single { it.id == conv }.unread)
        assertEquals(ruth.engine.safetyNumber(conv), kila.engine.safetyNumber(conv))
        // The sender stores its own copy; nothing is duplicated by later syncs.
        assertEquals(2, ruth.engine.messages(conv).size)
    }

    @Test
    fun bothPhonesStartingAtOnceStillAgree() = runBlocking {
        val a = phone("a")
        val b = phone("b")
        val conv = a.engine.open(b.userId)
        assertEquals(conv, b.engine.open(a.userId))
        val results = listOf(
            async(Dispatchers.IO) { a.engine.ensureReady(conv) },
            async(Dispatchers.IO) { b.engine.ensureReady(conv) },
        ).map { it.await() }
        assertEquals(1, results.count { it == Readiness.Ready }) // only the first Welcome wins
        val loser = if (results[0] == Readiness.Ready) b else a
        val winner = if (loser === a) b else a
        withTimeout(40_000) { while (loser.engine.ensureReady(conv) != Readiness.Ready) delay(300) }
        loser.engine.send(conv, Payload.text("from the slower phone"))
        winner.engine.send(conv, Payload.text("from the faster phone"))
        waitFor(winner, conv, "from the slower phone")
        waitFor(loser, conv, "from the faster phone")
    }

    @Test
    fun groupOfThreeWithPhotoAndVoice() = runBlocking {
        val pastor = phone("pastor")
        val bob = phone("bob")
        val cara = phone("cara")
        val dan = phone("dan")

        val (group, added) = pastor.engine.createGroup("Eriku Youth", listOf(bob.userId, cara.userId))
        assertEquals(listOf(bob.userId, cara.userId).toSet(), added.added.toSet())
        withTimeout(40_000) {
            while (bob.engine.ensureReady(group) != Readiness.Ready || cara.engine.ensureReady(group) != Readiness.Ready) delay(300)
        }
        bob.engine.send(group, Payload.text("Moning olgeta"))
        waitFor(pastor, group, "Moning olgeta")
        waitFor(cara, group, "Moning olgeta")
        assertEquals(bob.userId, cara.engine.messages(group).first { Payload.parse(it.payload).optString("body") == "Moning olgeta" }.sender)

        // Photo: encrypted on Cara's phone, opened on Bob's.
        val jpeg = ByteArray(40_000) { (it % 251).toByte() }
        assertEquals(true, cara.engine.sendImage(group, jpeg, 800, 600, byteArrayOf(1, 2), "Program for Sunday"))
        val photo = withTimeout(40_000) {
            var found: org.json.JSONObject? = null
            while (found == null) {
                found = bob.engine.messages(group).map { Payload.parse(it.payload) }.firstOrNull { it.optString("t") == "image" }
                if (found == null) delay(200)
            }
            found!!
        }
        assertEquals("Program for Sunday", photo.getString("body"))
        org.junit.Assert.assertArrayEquals(jpeg, bob.engine.mediaFile(photo).readBytes())

        // Voice note from the pastor reaches Cara.
        val audio = ByteArray(12_000) { 7 }
        pastor.engine.sendVoice(group, audio, 4_200)
        val voice = withTimeout(40_000) {
            var v: org.json.JSONObject? = null
            while (v == null) {
                v = cara.engine.messages(group).map { Payload.parse(it.payload) }.firstOrNull { it.optString("t") == "voice" }
                if (v == null) delay(200)
            }
            v!!
        }
        org.junit.Assert.assertArrayEquals(audio, cara.engine.mediaFile(voice).readBytes())

        // Dan joins later; Cara is removed and stops receiving.
        pastor.engine.addMembers(group, listOf(dan.userId))
        withTimeout(40_000) { while (dan.engine.ensureReady(group) != Readiness.Ready) delay(300) }
        pastor.engine.removeMembers(group, listOf(cara.userId))
        dan.engine.send(group, Payload.text("Tenkyu for adding me"))
        waitFor(bob, group, "Tenkyu for adding me")
        waitFor(pastor, group, "Tenkyu for adding me")
        delay(1_500)
        assertEquals(true, cara.engine.messages(group).none { Payload.parse(it.payload).optString("body") == "Tenkyu for adding me" })
        val info = pastor.engine.groupInfo(group, refresh = true)
        assertEquals(setOf(pastor.userId, bob.userId, dan.userId), info.members.map { it.id }.toSet())
        assertEquals(bob.engine.safetyNumber(group), dan.engine.safetyNumber(group))

        // Bob leaves; the pastor's phone takes him out of the encryption automatically.
        bob.engine.leaveGroup(group)
        withTimeout(20_000) { while (pastor.engine.groupInfo(group, refresh = true).epoch < 4) delay(300) }
        dan.engine.send(group, Payload.text("after Bob left"))
        waitFor(pastor, group, "after Bob left")
    }
}
