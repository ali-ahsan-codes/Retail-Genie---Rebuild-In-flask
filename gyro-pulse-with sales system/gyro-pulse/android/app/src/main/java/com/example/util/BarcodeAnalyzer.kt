package com.example.util

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.zxing.*
import com.google.zxing.common.HybridBinarizer

class BarcodeAnalyzer(
    private val onBarcodeScanned: (String) -> Unit
) : ImageAnalysis.Analyzer {

    private val reader = MultiFormatReader().apply {
        val hints = mapOf(
            DecodeHintType.POSSIBLE_FORMATS to listOf(
                BarcodeFormat.QR_CODE,
                BarcodeFormat.UPC_A,
                BarcodeFormat.UPC_E,
                BarcodeFormat.EAN_13,
                BarcodeFormat.EAN_8,
                BarcodeFormat.CODE_39,
                BarcodeFormat.CODE_128,
                BarcodeFormat.ITF
            ),
            DecodeHintType.TRY_HARDER to true
        )
        setHints(hints)
    }

    override fun analyze(image: ImageProxy) {
        try {
            val rotation = image.imageInfo.rotationDegrees
            val width = image.width
            val height = image.height
            val plane = image.planes[0]
            val buffer = plane.buffer
            val rowStride = plane.rowStride

            // Extract clean Y channel bytes, accounting for rowStride
            val cleanYData = ByteArray(width * height)
            for (y in 0 until height) {
                buffer.position(y * rowStride)
                val remaining = buffer.remaining()
                if (remaining > 0) {
                    buffer.get(cleanYData, y * width, minOf(width, remaining))
                }
            }

            // Rotate data based on CameraX image rotation
            val finalData: ByteArray
            val finalWidth: Int
            val finalHeight: Int

            when (rotation) {
                90 -> {
                    finalData = ByteArray(width * height)
                    for (y in 0 until height) {
                        for (x in 0 until width) {
                            finalData[x * height + (height - y - 1)] = cleanYData[y * width + x]
                        }
                    }
                    finalWidth = height
                    finalHeight = width
                }
                180 -> {
                    finalData = ByteArray(width * height)
                    for (i in 0 until width * height) {
                        finalData[i] = cleanYData[width * height - 1 - i]
                    }
                    finalWidth = width
                    finalHeight = height
                }
                270 -> {
                    finalData = ByteArray(width * height)
                    for (y in 0 until height) {
                        for (x in 0 until width) {
                            finalData[(width - x - 1) * height + y] = cleanYData[y * width + x]
                        }
                    }
                    finalWidth = height
                    finalHeight = width
                }
                else -> {
                    finalData = cleanYData
                    finalWidth = width
                    finalHeight = height
                }
            }

            val source = PlanarYUVLuminanceSource(
                finalData,
                finalWidth,
                finalHeight,
                0,
                0,
                finalWidth,
                finalHeight,
                false
            )
            val bitmap = BinaryBitmap(HybridBinarizer(source))

            val result = reader.decodeWithState(bitmap)
            onBarcodeScanned(result.text)
        } catch (_: ReaderException) {
            // No barcode found in this frame
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            reader.reset()
            image.close()
        }
    }
}
