/**
 * Prepare a user-selected drawing for upload: downscale so the longest side is
 * <= maxSide and re-encode, returning a small base64 data URL.
 *
 * Why: the backend traces line art, which needs no more than ~1200px; keeping the
 * payload small stays well under Vercel's request-body limit and is fast to send.
 * Transparent PNGs are flattened onto white so the server sees dark lines on light
 * paper (what its threshold expects).
 */
export async function fileToCompressedDataUrl(file, { maxSide = 1200, quality = 0.85 } = {}) {
  const src = await readAsDataUrl(file)
  const img = await loadImage(src)

  const scale = Math.min(1, maxSide / Math.max(img.width, img.height))
  const w = Math.max(1, Math.round(img.width * scale))
  const h = Math.max(1, Math.round(img.height * scale))

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff' // white paper behind any transparency
  ctx.fillRect(0, 0, w, h)
  ctx.drawImage(img, 0, 0, w, h)

  // Keep PNGs lossless (crisp line art); re-encode everything else as JPEG.
  const isPng = /image\/png/i.test(file.type)
  return canvas.toDataURL(isPng ? 'image/png' : 'image/jpeg', isPng ? undefined : quality)
}

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(reader.error || new Error('read failed'))
    reader.readAsDataURL(file)
  })
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('decode failed'))
    img.src = dataUrl
  })
}
