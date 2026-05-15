// King's Slicer: 3D Visualization for Stlux
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 2000);
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });

const container = document.getElementById('canvas-container');
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setClearColor(0x000000, 0);
container.appendChild(renderer.domElement);

const ambientLight = new THREE.AmbientLight(0x404040, 2);
scene.add(ambientLight);

const light1 = new THREE.DirectionalLight(0xffffff, 1);
light1.position.set(1, 1, 1);
scene.add(light1);

const light2 = new THREE.DirectionalLight(0xffcc00, 0.5);
light2.position.set(-1, -1, -1);
scene.add(light2);

camera.position.set(100, 100, 100);
camera.lookAt(0, 0, 0);

const grid = new THREE.GridHelper(200, 20, 0x444444, 0x222222);
scene.add(grid);

function animate() {
    requestAnimationFrame(animate);
    renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
    renderer.setSize(container.clientWidth, container.clientHeight);
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
});

// Function to load and display STL
function loadSTL(url) {
    // Clear existing meshes
    scene.children.forEach(child => {
        if (child.isMesh) scene.remove(child);
    });

    const loader = new THREE.STLLoader();
    loader.load(url, function (geometry) {
        const material = new THREE.MeshPhongMaterial({ color: 0xffcc00, specular: 0x111111, shininess: 200 });
        const mesh = new THREE.Mesh(geometry, material);

        geometry.computeBoundingBox();
        const center = new THREE.Vector3();
        geometry.boundingBox.getCenter(center);
        mesh.position.sub(center); // Center the model

        scene.add(mesh);

        // Adjust camera to fit
        const size = geometry.boundingBox.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        camera.position.set(maxDim * 2, maxDim * 2, maxDim * 2);
        camera.lookAt(0, 0, 0);
    });
}

// Expose to app.js
window.loadSTL = loadSTL;
