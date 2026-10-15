package pg.mcxus.app.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/** An error the server explained (e.g. "Not enough Stars"). [code] is the machine-readable reason. */
class ApiError(val status: Int, val code: String, override val message: String) : Exception(message)

/**
 * Minimal HTTP client on the platform's HttpURLConnection (no third-party libraries).
 * Every call runs off the main thread. Money actions send a fresh Idempotency-Key so a retry on a
 * bad connection never moves money twice.
 */
class Api(private val session: Session) {

    suspend fun get(path: String): String = call("GET", path, null, null)

    suspend fun obj(path: String): JSONObject = JSONObject(get(path))

    suspend fun list(path: String): JSONArray = JSONArray(get(path))

    suspend fun post(path: String, body: JSONObject? = null, idempotent: Boolean = false): JSONObject {
        val headers = if (idempotent) mapOf("Idempotency-Key" to UUID.randomUUID().toString()) else emptyMap()
        val text = call("POST", path, (body ?: JSONObject()).toString().toByteArray(), "application/json", headers)
        return if (text.isBlank()) JSONObject() else JSONObject(text)
    }

    suspend fun put(path: String, body: JSONObject): JSONObject =
        JSONObject(call("PUT", path, body.toString().toByteArray(), "application/json"))

    /** POST/PUT returning whatever JSON the server sends (e.g. a list). */
    suspend fun postRaw(path: String, body: JSONObject): String = call("POST", path, body.toString().toByteArray(), "application/json")

    suspend fun putRaw(path: String, body: JSONObject): String = call("PUT", path, body.toString().toByteArray(), "application/json")

    /** Upload raw bytes (an encrypted chat photo or voice note). */
    suspend fun postBytes(path: String, bytes: ByteArray): JSONObject =
        JSONObject(call("POST", path, bytes, "application/octet-stream"))

    /** Download raw bytes (an encrypted chat file). */
    suspend fun getBytes(path: String): ByteArray = withContext(Dispatchers.IO) {
        val conn = open(path)
        try {
            conn.requestMethod = "GET"
            val status = conn.responseCode
            if (status >= 400) throw parseError(status, conn.errorStream?.bufferedReader()?.use { it.readText() } ?: "")
            conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }

    private fun open(path: String): HttpURLConnection {
        val base = session.server.trimEnd('/')
        if (base.isEmpty()) throw IOException("No server set")
        return (URL(base + path).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 60_000
            session.token?.let { setRequestProperty("Authorization", "Bearer $it") }
        }
    }

    suspend fun delete(path: String): String = call("DELETE", path, null, null)

    /** multipart/form-data with text fields and JPEG files (all under the field name [fileField]). */
    suspend fun multipart(path: String, fields: Map<String, String>, jpegs: List<ByteArray>, fileField: String = "files"): JSONObject {
        val boundary = "----mcxus" + UUID.randomUUID().toString().replace("-", "")
        val out = ByteArrayOutputStream()
        fields.forEach { (name, value) ->
            out.write("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n".toByteArray())
            out.write(value.toByteArray(Charsets.UTF_8))
            out.write("\r\n".toByteArray())
        }
        jpegs.forEachIndexed { i, jpeg ->
            out.write("--$boundary\r\nContent-Disposition: form-data; name=\"$fileField\"; filename=\"photo$i.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".toByteArray())
            out.write(jpeg)
            out.write("\r\n".toByteArray())
        }
        out.write("--$boundary--\r\n".toByteArray())
        return JSONObject(call("POST", path, out.toByteArray(), "multipart/form-data; boundary=$boundary"))
    }

    /** Upload one JPEG as multipart/form-data field "file". */
    suspend fun upload(path: String, jpeg: ByteArray, filename: String = "photo.jpg"): JSONObject {
        val boundary = "----mcxus" + UUID.randomUUID().toString().replace("-", "")
        val out = ByteArrayOutputStream()
        out.write("--$boundary\r\n".toByteArray())
        out.write("Content-Disposition: form-data; name=\"file\"; filename=\"$filename\"\r\n".toByteArray())
        out.write("Content-Type: image/jpeg\r\n\r\n".toByteArray())
        out.write(jpeg)
        out.write("\r\n--$boundary--\r\n".toByteArray())
        return JSONObject(call("POST", path, out.toByteArray(), "multipart/form-data; boundary=$boundary"))
    }

    private suspend fun call(
        method: String,
        path: String,
        body: ByteArray?,
        contentType: String?,
        extraHeaders: Map<String, String> = emptyMap(),
    ): String = withContext(Dispatchers.IO) {
        val base = session.server.trimEnd('/')
        if (base.isEmpty()) throw IOException("No server set")
        val conn = URL(base + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 15_000
            conn.readTimeout = 30_000
            conn.setRequestProperty("Accept", "application/json")
            session.token?.let { conn.setRequestProperty("Authorization", "Bearer $it") }
            extraHeaders.forEach { (k, v) -> conn.setRequestProperty(k, v) }
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", contentType)
                conn.setFixedLengthStreamingMode(body.size)
                conn.outputStream.use { it.write(body) }
            }
            val status = conn.responseCode
            val stream = if (status >= 400) conn.errorStream else conn.inputStream
            val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
            if (status >= 400) throw parseError(status, text)
            text
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        /** Turn the server's error JSON into a readable message (also handles FastAPI validation errors). */
        fun parseError(status: Int, text: String): ApiError {
            return try {
                val json = JSONObject(text)
                when {
                    json.has("error") -> {
                        val e = json.getJSONObject("error")
                        ApiError(status, e.optString("code", "error"), e.optString("message", "Something went wrong"))
                    }
                    json.has("detail") && json.get("detail") is JSONArray -> {
                        val first = json.getJSONArray("detail").getJSONObject(0)
                        val loc = first.optJSONArray("loc")
                        val field = if (loc != null && loc.length() > 0) loc.get(loc.length() - 1).toString() else ""
                        val msg = first.optString("msg", "Invalid input")
                        ApiError(status, "invalid_input", if (field.isNotEmpty()) "$field: $msg" else msg)
                    }
                    else -> ApiError(status, "error", json.optString("detail", "Server error ($status)"))
                }
            } catch (e: Exception) {
                ApiError(status, "error", "Server error ($status)")
            }
        }
    }
}
