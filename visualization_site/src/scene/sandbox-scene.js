import * as THREE from "three";

const ACTION_CATEGORIES = ["Positioning", "Product", "Price", "Channel", "Promotion", "Retention"];

const ROLE_POSITIONS = Object.freeze({
  decision: new THREE.Vector3(0, 0.86, 0),
  synthesizer: new THREE.Vector3(2.72, 0.52, -0.38),
  critic: new THREE.Vector3(-2.72, 0.52, -0.38),
});

const STAR_LAYERS = Object.freeze([
  { count: 140, radius: 13.6, height: 7.8, size: 0.055, color: "#a9d7ff", opacity: 0.58, seed: 17 },
  { count: 96, radius: 9.8, height: 5.4, size: 0.085, color: "#f7e7a6", opacity: 0.72, seed: 47 },
  { count: 58, radius: 6.8, height: 3.4, size: 0.12, color: "#b5f1db", opacity: 0.76, seed: 83 },
]);

export class SandboxScene {
  constructor(container, agents) {
    this.container = container;
    this.agents = new Map();
    this.actionMarkers = new Map();
    this.starLayers = [];
    this.animationStartedAt = window.performance.now();
    this.activeAgentId = null;
    this.activeAgentRole = "";
    this.activeActions = new Set();

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#07101c");
    this.scene.fog = new THREE.Fog("#07101c", 10, 24);

    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 42);
    this.camera.position.set(0, 6.9, 10.2);
    this.camera.lookAt(0, 0.2, 0);

    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      preserveDrawingBuffer: true,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.14;
    this.renderer.domElement.dataset.sceneCanvas = "ready";
    this.container.append(this.renderer.domElement);

    this.overlay = document.createElement("div");
    this.overlay.className = "scene-overlay";
    this.container.append(this.overlay);

    this.createEnvironment();
    this.createStrategyPlatform();
    this.createAgents(agents);

    this.container.dataset.sceneReady = "true";
    this.container.dataset.agentCount = String(this.agents.size);
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
    this.animate();
  }

  setPlaybackView({ activeAgentId, activeAgentRole, bubble, actions }) {
    this.activeAgentId = this.resolveAgentId(activeAgentId, activeAgentRole);
    this.activeAgentRole = activeAgentRole || this.agents.get(this.activeAgentId)?.role || "";
    this.activeActions = new Set((actions || []).map((action) => action.category));
    this.container.dataset.activeRole = this.activeAgentRole || "idle";

    for (const [agentId, agent] of this.agents) {
      const isActive = agentId === this.activeAgentId;
      agent.active = isActive;
      agent.halo.material.opacity = isActive ? 0.9 : 0.22;
      agent.halo.scale.setScalar(isActive ? 1.2 : 1);
      agent.body.material.emissiveIntensity = isActive ? 0.96 : 0.28;
      agent.head.material.emissiveIntensity = isActive ? 0.5 : 0.16;
      agent.face.material.emissiveIntensity = isActive ? 0.24 : 0.08;
      agent.signal.traverse((child) => {
        if (child.material) {
          child.material.opacity = isActive ? child.userData.activeOpacity : child.userData.idleOpacity;
        }
      });
      agent.label.classList.toggle("is-active", isActive);
      agent.bubble.hidden = !isActive || !bubble;
      agent.bubble.textContent = isActive && bubble ? bubble : "";
    }

    for (const [category, marker] of this.actionMarkers) {
      const isActive = this.activeActions.has(category);
      marker.active = isActive;
      marker.core.material.emissiveIntensity = isActive ? 1.42 : 0.24;
      marker.ring.material.opacity = isActive ? 0.96 : 0.28;
      marker.label.classList.toggle("is-active", isActive);
    }
  }

  resolveAgentId(agentId, role) {
    if (agentId && this.agents.has(agentId)) {
      return agentId;
    }

    const matchingRole = role || (typeof agentId === "string" && agentId.startsWith("consumer-") ? "consumer" : "");
    if (!matchingRole) {
      return null;
    }

    const roleAgents = [...this.agents.values()].filter((agent) => agent.role === matchingRole);
    if (roleAgents.length === 0) {
      return null;
    }

    if (matchingRole === "consumer" && agentId) {
      return roleAgents[this.stableIndex(agentId, roleAgents.length)].id;
    }

    return roleAgents[0].id;
  }

  stableIndex(text, size) {
    let hash = 0;
    for (const character of String(text)) {
      hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
    }

    return hash % size;
  }

  createEnvironment() {
    const hemiLight = new THREE.HemisphereLight("#b7e5ff", "#050b14", 1.44);
    this.scene.add(hemiLight);

    const keyLight = new THREE.DirectionalLight("#ffe7ab", 3.6);
    keyLight.position.set(-4.2, 7.4, 6.4);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(1024, 1024);
    this.scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight("#78d9ff", 1.25);
    rimLight.position.set(5.2, 3.2, -5.4);
    this.scene.add(rimLight);

    const tableLight = new THREE.PointLight("#ffd87f", 34, 12, 1.8);
    tableLight.position.set(0, 1.52, 0);
    this.scene.add(tableLight);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(7.28, 128),
      new THREE.MeshStandardMaterial({
        color: "#0c2231",
        emissive: "#07131f",
        emissiveIntensity: 0.18,
        transparent: true,
        opacity: 0.88,
        roughness: 0.9,
        metalness: 0.02,
      }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.12;
    floor.receiveShadow = true;
    this.scene.add(floor);

    const trailRings = [
      { radius: 4.84, tube: 0.028, color: "#25506d", opacity: 0.6 },
      { radius: 6.18, tube: 0.018, color: "#b6f2dc", opacity: 0.22 },
    ];
    for (const ring of trailRings) {
      const mesh = new THREE.Mesh(
        new THREE.TorusGeometry(ring.radius, ring.tube, 12, 160),
        new THREE.MeshBasicMaterial({
          color: ring.color,
          transparent: true,
          opacity: ring.opacity,
        }),
      );
      mesh.rotation.x = Math.PI / 2;
      mesh.position.y = 0.012;
      this.scene.add(mesh);
    }

    this.createFireflyStarfield();
  }

  createFireflyStarfield() {
    for (const settings of STAR_LAYERS) {
      const positions = [];
      const bases = [];
      const phases = [];
      for (let index = 0; index < settings.count; index += 1) {
        const radius = settings.radius * (0.42 + seeded(settings.seed, index, 1) * 0.58);
        const angle = Math.PI * 2 * seeded(settings.seed, index, 2);
        const x = Math.cos(angle) * radius;
        const z = Math.sin(angle) * radius;
        const y = -0.18 + settings.height * seeded(settings.seed, index, 3);
        positions.push(x, y, z);
        bases.push(x, y, z);
        phases.push(Math.PI * 2 * seeded(settings.seed, index, 4));
      }

      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      const points = new THREE.Points(
        geometry,
        new THREE.PointsMaterial({
          color: settings.color,
          size: settings.size,
          sizeAttenuation: true,
          transparent: true,
          opacity: settings.opacity,
          depthWrite: false,
        }),
      );
      points.userData = {
        bases,
        phases,
        drift: 0.018 + settings.size * 0.08,
        sway: 0.03 + settings.size * 0.72,
      };
      this.starLayers.push(points);
      this.scene.add(points);
    }
  }

  createStrategyPlatform() {
    const platform = new THREE.Mesh(
      new THREE.CylinderGeometry(2.36, 2.64, 0.34, 96),
      new THREE.MeshStandardMaterial({
        color: "#dfc477",
        emissive: "#c17d1c",
        emissiveIntensity: 0.46,
        roughness: 0.44,
        metalness: 0.1,
      }),
    );
    platform.position.y = 0.14;
    platform.castShadow = true;
    platform.receiveShadow = true;
    this.scene.add(platform);
    this.platform = platform;

    const platformRing = new THREE.Mesh(
      new THREE.TorusGeometry(2.5, 0.064, 18, 128),
      new THREE.MeshBasicMaterial({
        color: "#fff0b6",
        transparent: true,
        opacity: 0.94,
      }),
    );
    platformRing.rotation.x = Math.PI / 2;
    platformRing.position.y = 0.34;
    this.scene.add(platformRing);
    this.platformRing = platformRing;

    this.strategyPulse = new THREE.Mesh(
      new THREE.RingGeometry(2.64, 2.72, 128),
      new THREE.MeshBasicMaterial({
        color: "#ffdda0",
        transparent: true,
        opacity: 0.12,
        side: THREE.DoubleSide,
      }),
    );
    this.strategyPulse.rotation.x = -Math.PI / 2;
    this.strategyPulse.position.y = 0.352;
    this.scene.add(this.strategyPulse);

    ACTION_CATEGORIES.forEach((category, index) => {
      const angle = (index / ACTION_CATEGORIES.length) * Math.PI * 2 - Math.PI / 2;
      const marker = new THREE.Group();
      marker.position.set(Math.cos(angle) * 2.05, 0.42, Math.sin(angle) * 2.05);

      const core = new THREE.Mesh(
        new THREE.CylinderGeometry(0.18, 0.18, 0.12, 32),
        new THREE.MeshStandardMaterial({
          color: "#eef7ec",
          emissive: "#5bc2a6",
          emissiveIntensity: 0.24,
          roughness: 0.42,
        }),
      );
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.24, 0.024, 12, 48),
        new THREE.MeshBasicMaterial({
          color: "#8ee2ca",
          transparent: true,
          opacity: 0.28,
        }),
      );
      ring.rotation.x = Math.PI / 2;
      core.castShadow = true;
      marker.add(core, ring);
      this.scene.add(marker);

      const label = document.createElement("span");
      label.className = "action-label";
      label.textContent = category;
      this.overlay.append(label);
      this.actionMarkers.set(category, { marker, core, ring, label, active: false });
    });
  }

  createAgents(agents) {
    const consumerCount = agents.filter((agent) => agent.role === "consumer").length;
    let consumerIndex = 0;
    for (const agent of agents) {
      let position = ROLE_POSITIONS[agent.role];
      if (agent.role === "consumer") {
        position = this.consumerPosition(consumerIndex, consumerCount);
        consumerIndex += 1;
      }
      this.addAgent(agent, position);
    }
  }

  consumerPosition(index, total) {
    const radius = total > 6 && index % 2 ? 4.12 : 3.84;
    const angle = Math.PI / 2 + (index / Math.max(total, 1)) * Math.PI * 2;
    return new THREE.Vector3(Math.cos(angle) * radius, 0.52, Math.sin(angle) * radius);
  }

  addAgent(agent, position) {
    const group = new THREE.Group();
    group.position.copy(position);
    const scale = agent.role === "decision" ? 1.16 : 1;
    const bodyHeight = 1.1 * scale;
    const headRadius = 0.34 * scale;

    const body = new THREE.Mesh(
      createRobeGeometry(scale),
      new THREE.MeshStandardMaterial({
        color: agent.color,
        emissive: agent.color,
        emissiveIntensity: 0.28,
        roughness: 0.44,
        metalness: 0.03,
      }),
    );
    body.castShadow = true;
    group.add(body);

    const collar = new THREE.Mesh(
      new THREE.TorusGeometry(0.25 * scale, 0.055 * scale, 18, 52),
      new THREE.MeshStandardMaterial({
        color: "#fff0c7",
        emissive: agent.color,
        emissiveIntensity: 0.22,
        roughness: 0.38,
      }),
    );
    collar.position.y = bodyHeight * 0.84;
    collar.rotation.x = Math.PI / 2;
    collar.scale.z = 0.58;
    group.add(collar);

    const head = new THREE.Mesh(
      new THREE.SphereGeometry(headRadius, 36, 36),
      new THREE.MeshStandardMaterial({
        color: "#fff1d4",
        emissive: "#ceae75",
        emissiveIntensity: 0.16,
        roughness: 0.34,
      }),
    );
    head.position.y = bodyHeight + headRadius * 0.72;
    head.scale.set(1.02, 0.96, 0.98);
    head.castShadow = true;
    group.add(head);

    const face = new THREE.Mesh(
      new THREE.SphereGeometry(headRadius * 0.72, 28, 24),
      new THREE.MeshStandardMaterial({
        color: "#fff7e6",
        emissive: "#efd8a0",
        emissiveIntensity: 0.08,
        roughness: 0.32,
      }),
    );
    face.position.set(0, head.position.y - headRadius * 0.07, headRadius * 0.56);
    face.scale.set(0.92, 0.7, 0.26);
    group.add(face);

    const eyes = [-1, 1].map((direction) => {
      const eye = new THREE.Mesh(
        new THREE.SphereGeometry(0.042 * scale, 16, 16),
        new THREE.MeshBasicMaterial({ color: "#2f3540" }),
      );
      eye.position.set(direction * 0.112 * scale, face.position.y + 0.018 * scale, headRadius * 0.785);
      eye.scale.y = 0.9;
      return eye;
    });
    const mouth = new THREE.Mesh(
      new THREE.TorusGeometry(0.064 * scale, 0.008 * scale, 8, 28, Math.PI),
      new THREE.MeshBasicMaterial({
        color: "#d8a05b",
        transparent: true,
        opacity: 0.72,
      }),
    );
    mouth.position.set(0, face.position.y - 0.105 * scale, headRadius * 0.79);
    mouth.rotation.z = Math.PI;
    group.add(...eyes, mouth);

    const glowShell = new THREE.Mesh(
      new THREE.SphereGeometry(headRadius * 1.2, 22, 22),
      new THREE.MeshBasicMaterial({
        color: agent.color,
        transparent: true,
        opacity: 0.09,
        side: THREE.BackSide,
      }),
    );
    glowShell.position.copy(head.position);
    group.add(glowShell);

    const halo = new THREE.Mesh(
      new THREE.TorusGeometry(agent.role === "decision" ? 0.84 : 0.64, 0.034, 12, 72),
      new THREE.MeshBasicMaterial({
        color: agent.color,
        transparent: true,
        opacity: 0.22,
      }),
    );
    halo.rotation.x = Math.PI / 2;
    halo.position.y = 0.07;
    group.add(halo);

    const signal = createRoleSignal(agent.role, agent.color, scale, head.position.y);
    group.add(signal);
    this.scene.add(group);

    const label = document.createElement("span");
    label.className = `agent-label role-${agent.role}`;
    label.textContent = agent.name;
    this.overlay.append(label);

    const bubble = document.createElement("div");
    bubble.className = `speech-bubble role-${agent.role}`;
    bubble.hidden = true;
    this.overlay.append(bubble);

    this.agents.set(agent.id, {
      ...agent,
      active: false,
      group,
      body,
      head,
      face,
      glowShell,
      halo,
      signal,
      label,
      bubble,
      basePosition: position.clone(),
      floatOffset: this.agents.size * 0.58,
      baseHeadY: head.position.y,
      headRadius,
    });
  }

  resize() {
    const width = Math.max(this.container.clientWidth, 1);
    const height = Math.max(this.container.clientHeight, 1);
    const aspect = width / height;
    const useNarrowFrame = aspect < 0.9;
    this.camera.aspect = width / height;
    this.camera.fov = useNarrowFrame ? 52 : 44;
    this.camera.position.set(0, useNarrowFrame ? 8.1 : 7.2, useNarrowFrame ? 13.8 : 11.3);
    this.camera.lookAt(0, 0.2, 0);
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  animate = () => {
    const elapsed = (window.performance.now() - this.animationStartedAt) / 1000;
    this.animationFrame = window.requestAnimationFrame(this.animate);

    for (const agent of this.agents.values()) {
      this.animateAgent(agent, elapsed);
    }

    this.animateStarfield(elapsed);
    this.animateStrategyPlatform(elapsed);
    this.renderer.render(this.scene, this.camera);
    this.updateOverlays();
  };

  animateAgent(agent, elapsed) {
    const phase = elapsed * 1.18 + agent.floatOffset;
    const speakingLift = agent.active ? 0.1 : 0;
    agent.group.position.y = agent.basePosition.y + Math.sin(phase) * 0.042 + speakingLift;
    agent.halo.rotation.z = elapsed * (agent.active ? 0.52 : 0.12) + agent.floatOffset;
    agent.glowShell.material.opacity = agent.active
      ? 0.14 + Math.sin(elapsed * 2.2 + agent.floatOffset) * 0.025
      : 0.07;
    agent.signal.rotation.y = elapsed * (agent.active ? 0.66 : 0.12) + agent.floatOffset * 0.22;
    agent.signal.scale.setScalar(agent.active ? 1 + Math.sin(elapsed * 2.35 + agent.floatOffset) * 0.08 : 1);
    agent.body.scale.set(1, agent.active ? 1.03 + Math.sin(elapsed * 2.1) * 0.02 : 1, 1);
    agent.head.rotation.z = agent.active
      ? Math.sin(elapsed * 1.8 + agent.floatOffset) * 0.045
      : Math.sin(phase * 0.62) * 0.018;

    if (agent.role === "decision" && agent.active) {
      agent.head.position.y = agent.baseHeadY + Math.sin(elapsed * 2.45) * 0.035;
    } else if (agent.role === "critic" && agent.active) {
      agent.body.rotation.z = -0.035 + Math.sin(elapsed * 1.72) * 0.024;
    } else if (agent.role === "synthesizer" && agent.active) {
      agent.body.rotation.z = Math.sin(elapsed * 1.34) * 0.028;
    } else {
      agent.head.position.y = agent.baseHeadY;
      agent.body.rotation.z *= 0.88;
    }
  }

  animateStarfield(elapsed) {
    for (const layer of this.starLayers) {
      const { bases, phases, sway, drift } = layer.userData;
      const position = layer.geometry.attributes.position;
      for (let index = 0; index < phases.length; index += 1) {
        const baseIndex = index * 3;
        const phase = phases[index];
        position.array[baseIndex] = bases[baseIndex] + Math.sin(elapsed * 0.24 + phase) * sway;
        position.array[baseIndex + 1] = bases[baseIndex + 1] + Math.sin(elapsed * 0.18 + phase * 1.8) * sway * 0.72;
        position.array[baseIndex + 2] = bases[baseIndex + 2] + Math.cos(elapsed * 0.2 + phase) * sway;
      }
      position.needsUpdate = true;
      layer.rotation.y = elapsed * drift;
    }
  }

  animateStrategyPlatform(elapsed) {
    const decisionActive = this.activeAgentRole === "decision" || this.activeActions.size > 0;
    this.platform.material.emissiveIntensity = decisionActive
      ? 0.54 + Math.sin(elapsed * 2.4) * 0.08
      : 0.42;
    this.platformRing.material.opacity = decisionActive
      ? 0.86 + Math.sin(elapsed * 2.2) * 0.1
      : 0.76;
    const pulseScale = decisionActive ? 1.02 + ((elapsed * 0.18) % 0.2) : 1;
    this.strategyPulse.scale.setScalar(pulseScale);
    this.strategyPulse.material.opacity = decisionActive
      ? 0.18 - ((elapsed * 0.18) % 0.12)
      : 0.08;

    for (const marker of this.actionMarkers.values()) {
      marker.ring.rotation.z += marker.active ? 0.02 : 0.004;
      marker.marker.position.y = 0.42 + (marker.active ? Math.sin(elapsed * 2.5) * 0.022 : 0);
    }
  }

  updateOverlays() {
    for (const agent of this.agents.values()) {
      this.placeOverlay(agent.label, agent.group, new THREE.Vector3(0, -0.22, 0));
      this.placeOverlay(agent.bubble, agent.head, new THREE.Vector3(0.4, 0.58, 0));
    }

    for (const marker of this.actionMarkers.values()) {
      this.placeOverlay(marker.label, marker.marker, new THREE.Vector3(0, 0.28, 0));
    }
  }

  placeOverlay(element, object, offset) {
    const worldPosition = new THREE.Vector3();
    object.getWorldPosition(worldPosition);
    worldPosition.add(offset);
    worldPosition.project(this.camera);

    const projectedX = (worldPosition.x * 0.5 + 0.5) * this.container.clientWidth;
    const projectedY = (-worldPosition.y * 0.5 + 0.5) * this.container.clientHeight;
    const horizontalInset = element.offsetWidth / 2 + 10;
    const verticalInset = element.offsetHeight / 2 + 10;
    const x = THREE.MathUtils.clamp(
      projectedX,
      Math.min(horizontalInset, this.container.clientWidth / 2),
      Math.max(this.container.clientWidth - horizontalInset, this.container.clientWidth / 2),
    );
    const y = THREE.MathUtils.clamp(
      projectedY,
      Math.min(verticalInset, this.container.clientHeight / 2),
      Math.max(this.container.clientHeight - verticalInset, this.container.clientHeight / 2),
    );
    const isVisible = worldPosition.z > -1 && worldPosition.z < 1;
    element.style.transform = `translate(-50%, -50%) translate(${x}px, ${y}px)`;
    element.style.visibility = isVisible ? "visible" : "hidden";
  }
}

function createRobeGeometry(scale) {
  const points = [
    new THREE.Vector2(0.02 * scale, 0),
    new THREE.Vector2(0.48 * scale, 0.02 * scale),
    new THREE.Vector2(0.38 * scale, 0.35 * scale),
    new THREE.Vector2(0.25 * scale, 0.75 * scale),
    new THREE.Vector2(0.18 * scale, 1.02 * scale),
    new THREE.Vector2(0.05 * scale, 1.1 * scale),
  ];
  return new THREE.LatheGeometry(points, 42);
}

function createRoleSignal(role, color, scale, headY) {
  const signal = new THREE.Group();
  if (role === "decision") {
    addSignalMesh(
      signal,
      new THREE.TorusGeometry(0.34 * scale, 0.025 * scale, 12, 64),
      "#ffe7a2",
      { y: headY + 0.46 * scale, rotationX: Math.PI / 2, idleOpacity: 0.42, activeOpacity: 0.96 },
    );
    addSignalMesh(
      signal,
      new THREE.OctahedronGeometry(0.09 * scale, 1),
      "#fff0bd",
      { y: headY + 0.46 * scale, idleOpacity: 0.34, activeOpacity: 1 },
    );
    return signal;
  }

  if (role === "synthesizer") {
    [-1, 0, 1].forEach((slot) => {
      addSignalMesh(
        signal,
        new THREE.TorusGeometry((0.31 + Math.abs(slot) * 0.08) * scale, 0.018 * scale, 10, 52, Math.PI * 1.16),
        "#8de7ea",
        {
          x: slot * 0.05,
          y: headY - 0.02 + slot * 0.07,
          rotationZ: Math.PI * (0.18 + slot * 0.08),
          idleOpacity: 0.18,
          activeOpacity: 0.82,
        },
      );
    });
    return signal;
  }

  if (role === "critic") {
    addSignalMesh(
      signal,
      new THREE.TorusGeometry(0.48 * scale, 0.022 * scale, 12, 72, Math.PI * 1.42),
      "#f0a16f",
      { y: 0.46 * scale, rotationX: Math.PI / 2, rotationZ: -0.66, idleOpacity: 0.24, activeOpacity: 0.9 },
    );
    addSignalMesh(
      signal,
      new THREE.ConeGeometry(0.07 * scale, 0.16 * scale, 3),
      "#ffd29a",
      { x: -0.38 * scale, y: 0.52 * scale, z: 0.16, rotationZ: 0.44, idleOpacity: 0.2, activeOpacity: 0.94 },
    );
    return signal;
  }

  addSignalMesh(
    signal,
    new THREE.TorusGeometry(0.24 * scale, 0.018 * scale, 10, 54),
    color,
    { y: headY + 0.02, rotationY: Math.PI / 2, idleOpacity: 0.16, activeOpacity: 0.68 },
  );
  return signal;
}

function addSignalMesh(group, geometry, color, options) {
  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: options.idleOpacity,
    }),
  );
  mesh.position.set(options.x || 0, options.y || 0, options.z || 0);
  mesh.rotation.set(options.rotationX || 0, options.rotationY || 0, options.rotationZ || 0);
  mesh.userData.idleOpacity = options.idleOpacity;
  mesh.userData.activeOpacity = options.activeOpacity;
  group.add(mesh);
}

function seeded(seed, index, channel) {
  const value = Math.sin(seed * 92.41 + index * 17.37 + channel * 41.73) * 43758.5453;
  return value - Math.floor(value);
}
