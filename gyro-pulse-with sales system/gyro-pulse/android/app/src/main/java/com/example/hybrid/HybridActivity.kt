package com.example.hybrid

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.text.InputFilter
import android.text.InputType
import android.view.WindowManager
import android.widget.*
import java.util.concurrent.Executors

/** Isolated connected-mode operator pilot; legacy viewmodel/sync/GPC flow is not started. */
class HybridActivity : Activity() {
    private lateinit var engine: HybridEngine
    private lateinit var status: TextView
    private lateinit var orderId: EditText
    private val executor = Executors.newSingleThreadExecutor()
    private var pendingExport: ByteArray? = null
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 24, 24, 24) }
        setContentView(ScrollView(this).apply { addView(layout) })
        status = TextView(this); layout.addView(status)
        try { engine = HybridEngine(this) } catch (error: Exception) { status.text = "Keystore/state unavailable. Do not reset or delete retained orders. Operator recovery required."; return }
        val inputs = mutableListOf<EditText>()
        val captured = ThreadLocal<Map<EditText,String>>()
        fun value(field: EditText): String = captured.get()!!.getValue(field)
        fun input(hint: String, limit: Int): EditText = EditText(this).apply {
            this.hint = hint; filters = arrayOf(InputFilter.LengthFilter(limit)); isSaveEnabled = false
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            if (android.os.Build.VERSION.SDK_INT >= 26) importantForAutofill = android.view.View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
            inputs.add(this); layout.addView(this)
        }
        fun button(title: String, work: () -> String) { layout.addView(Button(this).apply { text = title; setOnClickListener { val snapshot = inputs.associateWith { it.text.toString() }; executor.execute {
            captured.set(snapshot)
            val result = try { work() } catch (error: Exception) { "Operation rejected/failed. Retained orders unchanged unless a cloud receipt was verified. Check identity, scope, catalog, network and keys; no automatic fallback." }
            captured.remove()
            runOnUiThread { if (!isFinishing) status.text = result }
        } } }) }
        status.text = engine.summary()
        val cloud = input("Operator-approved HTTPS cloud origin", 300)
        val grant = input("Private single-use enrollment JSON", 16384)
        button("Enroll / rotate device bearer") { engine.enroll(value(cloud), value(grant)); runOnUiThread { grant.text.clear() }; engine.summary() }
        val store = input("Native store ID", 64)
        button("Download read-only catalog") { engine.downloadCatalog(value(store)) }
        val proposal = input("Immutable order JSON (review before queueing)", 14000)
        button("Create NEW proposal template") { val value = engine.proposalTemplate(value(store)); runOnUiThread { proposal.setText(value) }; "New business ID generated; fill customer and quantities. Do not recreate IDs for retries." }
        orderId = input("Retained business order UUID for export/LAN", 36)
        button("Persist signed offline order") { val id = engine.queue(value(proposal)); runOnUiThread { orderId.setText(id) }; "Order encrypted and retained: $id. Not delivered or approved." }
        button("Reconcile with enrolled cloud") { engine.syncCloud() }
        button("Send encrypted parcel to enrolled office HTTPS") { engine.sendLan(value(orderId)) }
        button("Export encrypted office parcel (.rgx)") {
            val parcel = engine.officeParcel(value(orderId)).toByteArray(Charsets.UTF_8)
            pendingExport = parcel
            runOnUiThread { startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply { addCategory(Intent.CATEGORY_OPENABLE); type = "application/octet-stream"; putExtra(Intent.EXTRA_TITLE, "field-order.rgx") }, 6001) }
            "Choose a controlled destination; encrypted export does not acknowledge/delete the order."
        }
        button("Show device identity / retained count") { engine.summary() }
    }
    @Deprecated("Pilot uses platform SAF result")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val bytes = pendingExport; pendingExport = null
        if (requestCode == 6001 && resultCode == RESULT_OK && data?.data != null && bytes != null) executor.execute {
            val message = try { contentResolver.openOutputStream(data.data!!, "w").use { output -> check(output != null); output.write(bytes) }; "Encrypted parcel exported; order retained. Native approval unknown." } catch (error: Exception) { "Export failed; order remains encrypted locally." }
            runOnUiThread { if (!isFinishing) status.text = message }
        }
    }
    override fun onDestroy() { executor.shutdown(); super.onDestroy() }
}
