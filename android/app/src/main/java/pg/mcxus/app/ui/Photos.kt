package pg.mcxus.app.ui

import android.Manifest
import android.content.ContentValues
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import pg.mcxus.app.LocalApp
import pg.mcxus.app.util.Images

/** "Take photo" / "Gallery" buttons: shrink on the phone, then upload to the listing (max 5 photos). */
@Composable
fun PhotoButtons(listingId: String, onUploaded: () -> Unit) {
    val app = LocalApp.current
    val context = LocalContext.current
    var cameraUri by remember { mutableStateOf<Uri?>(null) }
    var busy by remember { mutableStateOf(false) }

    fun upload(uri: Uri) {
        busy = true
        app.launch(onDone = { busy = false }) {
            val jpeg = withContext(Dispatchers.Default) { Images.prepareUpload(context.contentResolver, uri) }
            app.api.upload("/v1/listings/$listingId/photos", jpeg)
            app.say("Photo added")
            onUploaded()
        }
    }

    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri -> uri?.let(::upload) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> if (ok) cameraUri?.let(::upload) }

    fun openCamera() {
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "mcxus_${System.currentTimeMillis()}.jpg")
            put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
        }
        cameraUri = context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
        cameraUri?.let { camera.launch(it) } ?: app.say("Could not open the camera")
    }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) openCamera() else app.say("Storage permission is needed to save camera photos on this Android version")
    }

    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        LineButton(if (busy) "Uploading…" else "Take photo", enabled = !busy, modifier = Modifier.weight(1f), onClick = {
            val needsStorage = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
                context.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
            if (needsStorage) permission.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE) else openCamera()
        })
        LineButton("From gallery", enabled = !busy, modifier = Modifier.weight(1f), onClick = {
            gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
        })
    }
}
