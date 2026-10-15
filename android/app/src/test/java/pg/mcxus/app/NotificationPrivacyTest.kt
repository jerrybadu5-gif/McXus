package pg.mcxus.app

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import pg.mcxus.app.net.Session

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class NotificationPrivacyTest {
    @Test
    fun notificationsSayOnlyNewMessageByDefault() {
        val session = Session(ApplicationProvider.getApplicationContext(), "privacy-test")
        assertEquals(false, session.showPreviews)
        session.showPreviews = true
        assertEquals(true, Session(ApplicationProvider.getApplicationContext(), "privacy-test").showPreviews)
    }
}
