/**
 * A page's generation result. Users can redraw a page several times; we keep every
 * attempt as a "variant" so a worse redraw never destroys a better earlier drawing.
 *
 * Shape: { variants: [{ imageUrl, stlUrl }, ...], selected: <index> }
 *
 * Legacy sessions (localStorage) stored a single { imageUrl, stlUrl }. The helpers
 * below normalize that on read, so old saved books keep working with no migration.
 */

/** All variants, newest last. Tolerates the legacy single-object shape. */
export function variantsOf(res) {
  if (!res) return []
  if (Array.isArray(res.variants)) return res.variants
  if (res.imageUrl || res.stlUrl) return [{ imageUrl: res.imageUrl, stlUrl: res.stlUrl }]
  return []
}

/** Clamped index of the chosen variant, or -1 when there are none. Defaults to newest. */
export function selectedIndex(res) {
  const n = variantsOf(res).length
  if (n === 0) return -1
  const i = res?.selected ?? n - 1
  return Math.min(Math.max(i, 0), n - 1)
}

/** The variant the user has chosen (its STL is the one that gets downloaded). */
export function chosenVariant(res) {
  const i = selectedIndex(res)
  return i >= 0 ? variantsOf(res)[i] : null
}

/** Append a freshly generated variant and select it. */
export function addVariant(res, variant) {
  const variants = [...variantsOf(res), variant]
  return { variants, selected: variants.length - 1 }
}

/** Return `res` with a different variant selected (index clamped to range). */
export function selectVariant(res, index) {
  const n = variantsOf(res).length
  if (n === 0) return res
  return { variants: variantsOf(res), selected: Math.min(Math.max(index, 0), n - 1) }
}
