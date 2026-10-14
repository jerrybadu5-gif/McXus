package pg.mcxus.app.ui

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import kotlinx.coroutines.launch
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import pg.mcxus.app.BuildConfig
import pg.mcxus.app.LocalApp
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Place
import pg.mcxus.app.util.Places

/**
 * Choose where people meet or deliver: GPS first ("Use my current location" or "Set on map"),
 * then an address/landmark that people recognise. [requirePng] keeps points inside PNG (the server's rule).
 */
@Composable
fun PlaceField(
    title: String,
    place: Place,
    onChange: (Place) -> Unit,
    modifier: Modifier = Modifier,
    hint: String = "Pick a busy public place, not your home.",
    requirePng: Boolean = true,
) {
    val app = LocalApp.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var locating by remember { mutableStateOf(false) }
    var mapOpen by remember { mutableStateOf(false) }

    fun accept(p: Place) {
        if (requirePng && p.hasPoint && !p.inPng) {
            app.say("That point is outside Papua New Guinea. Set it on the map instead.")
            return
        }
        onChange(p)
        if (p.address.isBlank() && p.hasPoint) scope.launch {
            val guess = Places.describe(context, p.latitude!!.toDouble(), p.longitude!!.toDouble())
            if (guess.isNotEmpty()) onChange(p.copy(address = guess))
        }
    }

    fun locate() {
        if (!Places.locationOn(context)) {
            app.say("Turn on Location in your phone's quick settings, then try again.")
            return
        }
        locating = true
        scope.launch {
            val fix = Places.current(context)
            locating = false
            if (fix == null) app.say("Could not get a GPS fix. Go near a window or outside, or set the point on the map.")
            else accept(Place.of(fix.latitude, fix.longitude, place.address))
        }
    }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        if (granted.values.any { it }) locate() else app.say("Location permission was not given. You can set the point on the map.")
    }

    Column(
        modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Color.White).border(1.dp, Mx.Field, RoundedCornerShape(16.dp))
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Ic.Pin, null, tint = Mx.Blue, modifier = Modifier.size(20.dp))
            Text(title, fontWeight = FontWeight.Bold, fontSize = 15.sp, modifier = Modifier.weight(1f))
            if (place.hasPoint) {
                Text("Clear", color = Mx.Muted, fontSize = 13.sp, modifier = Modifier.clip(RoundedCornerShape(8.dp))
                    .clickable { onChange(place.copy(latitude = null, longitude = null)) }.padding(4.dp))
            }
        }
        if (place.hasPoint) {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Mx.Tint).padding(10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(Ic.Check, null, tint = Mx.Green, modifier = Modifier.size(18.dp))
                Column(Modifier.weight(1f)) {
                    Text("GPS point set", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    Text(place.coordinates(), fontSize = 12.sp, color = Mx.Muted, modifier = Modifier.testTag("place-coordinates"))
                }
                Text("View", color = Mx.Blue, fontWeight = FontWeight.Bold, fontSize = 13.sp,
                    modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable { Places.openInMaps(context, place, title) }.padding(6.dp))
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LineButton(if (locating) "Finding you…" else "Use my location", enabled = !locating, modifier = Modifier.weight(1f).testTag("use-my-location"), onClick = {
                if (Places.hasPermission(context)) locate()
                else permission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
            })
            LineButton("Set on map", modifier = Modifier.weight(1f).testTag("set-on-map"), onClick = { mapOpen = true })
        }
        Field(place.address, { onChange(place.copy(address = it.take(200))) }, "Address or landmark (e.g. Eriku market gate)", tag = "place-address")
        Text(hint, fontSize = 12.sp, color = Mx.Muted)
    }

    if (mapOpen) MapPicker(start = place.takeIf { it.hasPoint }, onDismiss = { mapOpen = false }) { lat, lng ->
        mapOpen = false
        accept(Place.of(lat, lng, place.address))
    }
}

/** Full-screen OpenStreetMap: drag the map until the pin is on the meeting spot, then confirm. */
@Composable
fun MapPicker(start: Place?, onDismiss: () -> Unit, onPick: (Double, Double) -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    val map = remember {
        Configuration.getInstance().apply {
            userAgentValue = BuildConfig.APPLICATION_ID // required by the OpenStreetMap tile usage policy
            osmdroidBasePath = context.cacheDir.resolve("osmdroid")
            osmdroidTileCache = context.cacheDir.resolve("osmdroid/tiles") // tiles are cached to save data
        }
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            zoomController.setVisibility(org.osmdroid.views.CustomZoomButtonsController.Visibility.SHOW_AND_FADEOUT)
            val p = start ?: Places.DEFAULT
            controller.setZoom(if (start != null) 17.0 else 12.0)
            controller.setCenter(GeoPoint(p.latitude!!.toDouble(), p.longitude!!.toDouble()))
        }
    }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, e ->
            if (e == Lifecycle.Event.ON_RESUME) map.onResume()
            if (e == Lifecycle.Event.ON_PAUSE) map.onPause()
        }
        lifecycle.addObserver(observer)
        map.onResume()
        onDispose {
            lifecycle.removeObserver(observer)
            map.onPause()
            map.onDetach()
        }
    }
    if (start == null && Places.hasPermission(context)) {
        androidx.compose.runtime.LaunchedEffect(Unit) {
            Places.current(context, 10_000)?.let { map.controller.animateTo(GeoPoint(it.latitude, it.longitude), 17.0, 600L) }
        }
    }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Box(Modifier.fillMaxSize().background(Mx.Bg)) {
            AndroidView({ map }, Modifier.fillMaxSize().testTag("map"))
            // The pin stays in the middle; the map moves under it.
            Icon(Ic.PinSolid, contentDescription = "Meeting point", tint = Mx.Navy,
                modifier = Modifier.align(Alignment.Center).offset(y = (-20).dp).size(44.dp))
            Box(Modifier.align(Alignment.Center).size(8.dp).clip(RoundedCornerShape(4.dp)).background(Mx.Gold))
            Row(
                Modifier.fillMaxWidth().statusBarsPadding().padding(12.dp).clip(RoundedCornerShape(16.dp)).background(Color.White).padding(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onDismiss) { Icon(Ic.Back, "Close map", tint = Mx.Ink) }
                Text("Move the map so the pin is on the meeting spot", fontSize = 13.sp, modifier = Modifier.weight(1f))
            }
            Column(
                Modifier.align(Alignment.BottomCenter).fillMaxWidth().navigationBarsPadding().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                    RoundIcon(Ic.Locate, "Go to my location", onClick = {
                        scope.launch {
                            Places.current(context, 15_000)?.let { map.controller.animateTo(GeoPoint(it.latitude, it.longitude), 17.0, 600L) }
                        }
                    })
                }
                BigButton("Use this point", modifier = Modifier.testTag("use-this-point"), onClick = {
                    val c = map.mapCenter
                    onPick(c.latitude, c.longitude)
                })
                Text("Map © OpenStreetMap contributors", fontSize = 10.sp, color = Mx.Muted,
                    modifier = Modifier.align(Alignment.End).clip(RoundedCornerShape(4.dp)).background(Color.White).padding(horizontal = 4.dp))
            }
        }
    }
}

/** Read-only card for a meet-up / delivery place with a Directions button. */
@Composable
fun PlaceCard(title: String, place: Place, modifier: Modifier = Modifier, note: String = "", action: (@Composable () -> Unit)? = null) {
    val context = LocalContext.current
    Row(
        modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).border(1.dp, Mx.Line, RoundedCornerShape(14.dp)).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(42.dp).clip(RoundedCornerShape(12.dp)).background(Mx.Tint), contentAlignment = Alignment.Center) {
            Icon(Ic.Pin, null, tint = Mx.Blue, modifier = Modifier.size(22.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(title, fontSize = 12.sp, color = Mx.Muted)
            Text(place.address.ifBlank { "GPS point" }, fontWeight = FontWeight.Bold, fontSize = 14.sp)
            if (place.hasPoint) Text(place.coordinates(), fontSize = 11.sp, color = Mx.Muted)
            if (note.isNotEmpty()) Text(note, fontSize = 12.sp, color = Mx.Muted)
            action?.invoke()
        }
        Text(
            "Directions", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp,
            modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(Mx.Blue).clickable { Places.openInMaps(context, place, title) }
                .padding(horizontal = 12.dp, vertical = 9.dp).testTag("directions"),
        )
    }
}
