package pg.mcxus.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import pg.mcxus.app.App
import pg.mcxus.app.LocalApp

fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

fun JSONObject.str(key: String): String = if (!has(key) || isNull(key)) "" else optString(key, "")

/** Data a screen fetches from the server, with loading and error states and a reload(). */
class Loader<T>(private val app: App, private val scope: CoroutineScope, private val fetch: suspend () -> T) {
    var data by mutableStateOf<T?>(null)
    var error by mutableStateOf<String?>(null)
    var loading by mutableStateOf(false)

    fun reload() {
        scope.launch {
            loading = true
            try {
                data = fetch()
                error = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                error = app.explain(e)
            } finally {
                loading = false
            }
        }
    }
}

@Composable
fun <T> rememberLoader(vararg keys: Any?, fetch: suspend () -> T): Loader<T> {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    val loader = remember(*keys) { Loader(app, scope, fetch) }
    LaunchedEffect(loader) { loader.reload() }
    return loader
}
