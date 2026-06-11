import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

/**
 * Rotatable 3D preview of a page STL. Loads the mesh from `url`, lays it flat,
 * fits the camera, and lets the user orbit/zoom. Cleans up WebGL on unmount.
 */
export function StlViewer({ url, className = '' }) {
  const mountRef = useRef(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!url || !mount) return

    const width = mount.clientWidth || 400
    const height = mount.clientHeight || 360

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0xfffbf5)

    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 5000)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(width, height)
    mount.appendChild(renderer.domElement)

    scene.add(new THREE.AmbientLight(0xffffff, 0.75))
    const key = new THREE.DirectionalLight(0xffffff, 0.9)
    key.position.set(1, 1.5, 2)
    scene.add(key)
    const fill = new THREE.DirectionalLight(0xffffff, 0.35)
    fill.position.set(-1, -0.5, -1)
    scene.add(fill)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.autoRotate = true
    controls.autoRotateSpeed = 1.2

    let mesh
    let raf
    let disposed = false

    new STLLoader().load(url, (geometry) => {
      if (disposed) return
      geometry.computeVertexNormals()
      geometry.center()
      const material = new THREE.MeshStandardMaterial({
        color: 0xea580c,
        roughness: 0.65,
        metalness: 0.05,
      })
      mesh = new THREE.Mesh(geometry, material)
      mesh.rotation.x = -Math.PI / 2 // lay the plate flat, relief facing up
      scene.add(mesh)

      const sphere = new THREE.Box3().setFromObject(mesh).getBoundingSphere(new THREE.Sphere())
      const r = sphere.radius || 75
      camera.position.set(0, r * 1.1, r * 1.6)
      camera.lookAt(0, 0, 0)
      controls.update()
    })

    const animate = () => {
      raf = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    const onResize = () => {
      const w = mount.clientWidth || width
      const h = mount.clientHeight || height
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      controls.dispose()
      if (mesh) {
        mesh.geometry.dispose()
        mesh.material.dispose()
      }
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
    }
  }, [url])

  return (
    <div
      ref={mountRef}
      role="img"
      aria-label="תצוגה תלת־ממדית של העמוד — אפשר לסובב"
      className={`rounded-card border-line bg-paper overflow-hidden border ${className}`}
    />
  )
}
