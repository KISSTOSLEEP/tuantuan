/**
 * 团团3D熊猫引擎 🐼
 * Three.js 构建的立体熊猫，支持表情/动画/自定义形象
 */
(function (global) {
  'use strict';

  // ========== 3D 熊猫构建器 ==========
  class Panda3D {
    constructor(containerEl, config) {
      this.container = containerEl;
      this.config = Object.assign({
        furColor: 0xffffff,       // 毛色 (白)
        earColor: 0x222222,       // 耳朵黑
        eyeWhite: 0xffffff,       // 眼白
        pupilColor: 0x111111,     // 瞳孔
        blushColor: 0xffaaaa,     // 腮红
        noseColor: 0x333333,      // 鼻子
        accessory: 'none',        // 配饰: none | bow | scarf | bamboo
        sceneBg: 'forest',        // 场景: forest | starry | room
      }, config || {});

      this.scene = null;
      this.camera = null;
      this.renderer = null;
      this.panda = null;
      this.accessories = {};
      this.animState = 'idle';     // idle | talking | happy | sad | wave
      this.animTime = 0;
      this.clock = 0;
      this.mouth = null;
      this.arms = [];
      this.ears = [];
      this.headGroup = null;
      this.bodyGroup = null;
      this.faceGroup = null;
      this.blushL = null;
      this.blushR = null;
      this.currentAccessory = null;

      this._init();
    }

    _init() {
      const rect = this.container.getBoundingClientRect();
      const w = rect.width || 200;
      const h = rect.height || 200;

      // 场景
      this.scene = new THREE.Scene();

      // 相机
      this.camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 100);
      this.camera.position.set(0, 0.5, 5);
      this.camera.lookAt(0, 0.5, 0);

      // 渲染器
      this.renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
      });
      this.renderer.setSize(w, h);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      this.container.appendChild(this.renderer.domElement);

      // 灯光
      const ambient = new THREE.AmbientLight(0xffffff, 0.6);
      this.scene.add(ambient);

      const mainLight = new THREE.DirectionalLight(0xffffff, 1.0);
      mainLight.position.set(3, 5, 4);
      mainLight.castShadow = true;
      this.scene.add(mainLight);

      const fillLight = new THREE.DirectionalLight(0xffeedd, 0.4);
      fillLight.position.set(-2, 1, 3);
      this.scene.add(fillLight);

      const rimLight = new THREE.DirectionalLight(0xffffff, 0.3);
      rimLight.position.set(-1, 2, -3);
      this.scene.add(rimLight);

      // 背景
      this._buildScene();

      // 熊猫
      this._buildPanda();

      // 动画循环
      this._animate();

      // 窗口大小变化
      this._handleResize();
    }

    _buildScene() {
      // 地面阴影
      const groundGeo = new THREE.CircleGeometry(3, 32);
      const groundMat = new THREE.MeshStandardMaterial({
        color: this.config.sceneBg === 'forest' ? 0x8fbc8f :
               this.config.sceneBg === 'starry' ? 0x1a1a2e : 0xd4c9b0,
        transparent: true,
        opacity: 0.3,
        side: THREE.DoubleSide,
      });
      const ground = new THREE.Mesh(groundGeo, groundMat);
      ground.rotation.x = -Math.PI / 2;
      ground.position.y = -0.5;
      ground.receiveShadow = true;
      this.scene.add(ground);

      // 场景装饰
      if (this.config.sceneBg === 'forest') {
        this._addForestElements();
      } else if (this.config.sceneBg === 'starry') {
        this._addStarElements();
      } else {
        this._addRoomElements();
      }
    }

    _addForestElements() {
      // 竹子装饰
      for (let i = 0; i < 3; i++) {
        const stick = new THREE.Mesh(
          new THREE.CylinderGeometry(0.02, 0.03, 0.8, 6),
          new THREE.MeshStandardMaterial({ color: 0x4a7c59 })
        );
        stick.position.set(-1.2 + i * 0.6, -0.1, -1.5);
        stick.castShadow = true;
        this.scene.add(stick);

        const leaf = new THREE.Mesh(
          new THREE.SphereGeometry(0.08, 4, 4),
          new THREE.MeshStandardMaterial({ color: 0x6aaa5a })
        );
        leaf.position.set(-1.2 + i * 0.6, 0.35, -1.5);
        leaf.scale.set(1, 0.3, 1);
        this.scene.add(leaf);
      }
    }

    _addStarElements() {
      for (let i = 0; i < 20; i++) {
        const star = new THREE.Mesh(
          new THREE.SphereGeometry(0.02, 4, 4),
          new THREE.MeshStandardMaterial({
            color: 0xffffcc,
            emissive: 0xffffaa,
            emissiveIntensity: 0.5,
          })
        );
        star.position.set(
          (Math.random() - 0.5) * 4,
          Math.random() * 2,
          -2 - Math.random() * 1
        );
        this.scene.add(star);
      }
    }

    _addRoomElements() {
      // 小窗台
      const shelf = new THREE.Mesh(
        new THREE.BoxGeometry(1.2, 0.04, 0.08),
        new THREE.MeshStandardMaterial({ color: 0x8B7355 })
      );
      shelf.position.set(0, -0.4, -1.2);
      this.scene.add(shelf);
    }

    _buildPanda() {
      this.panda = new THREE.Group();
      const cfg = this.config;

      // ----- 身体 -----
      const bodyMat = new THREE.MeshStandardMaterial({ color: cfg.furColor, roughness: 0.6, metalness: 0.0 });
      const darkMat = new THREE.MeshStandardMaterial({ color: cfg.earColor, roughness: 0.7 });
      const pinkMat = new THREE.MeshStandardMaterial({ color: cfg.blushColor, transparent: true, opacity: 0.5, roughness: 0.4 });
      const whiteMat = new THREE.MeshStandardMaterial({ color: cfg.eyeWhite, roughness: 0.3 });
      const pupilMat = new THREE.MeshStandardMaterial({ color: cfg.pupilColor, roughness: 0.1 });
      const noseMat = new THREE.MeshStandardMaterial({ color: cfg.noseColor, roughness: 0.8 });

      // 身体 (椭圆)
      this.bodyGroup = new THREE.Group();
      const body = new THREE.Mesh(new THREE.SphereGeometry(0.5, 20, 20), bodyMat);
      body.scale.set(1, 0.9, 0.75);
      body.position.y = 0.1;
      body.castShadow = true;
      this.bodyGroup.add(body);

      // 肚子白色区域
      const bellyMat = new THREE.MeshStandardMaterial({ color: 0xf5f5f5, roughness: 0.5 });
      const belly = new THREE.Mesh(new THREE.SphereGeometry(0.32, 16, 16), bellyMat);
      belly.scale.set(0.9, 0.8, 0.5);
      belly.position.set(0, 0.05, 0.45);
      this.bodyGroup.add(belly);

      // 腿 (黑色)
      const legMat = darkMat;
      const legGeo = new THREE.SphereGeometry(0.16, 12, 12);
      const legL = new THREE.Mesh(legGeo, legMat);
      legL.position.set(-0.2, -0.3, 0.2);
      legL.scale.set(0.9, 0.6, 1);
      legL.castShadow = true;
      this.bodyGroup.add(legL);

      const legR = new THREE.Mesh(legGeo, legMat);
      legR.position.set(0.2, -0.3, 0.2);
      legR.scale.set(0.9, 0.6, 1);
      legR.castShadow = true;
      this.bodyGroup.add(legR);

      this.panda.add(this.bodyGroup);

      // ----- 头 -----
      this.headGroup = new THREE.Group();
      this.headGroup.position.y = 0.55;

      const head = new THREE.Mesh(new THREE.SphereGeometry(0.4, 24, 24), bodyMat);
      head.scale.set(1, 0.85, 0.85);
      head.castShadow = true;
      this.headGroup.add(head);

      // 耳朵
      const earGeo = new THREE.SphereGeometry(0.13, 12, 12);
      const earL = new THREE.Mesh(earGeo, darkMat);
      earL.position.set(-0.3, 0.25, 0);
      earL.scale.set(0.9, 0.5, 0.7);
      this.headGroup.add(earL);
      this.ears = [earL];

      const earR = new THREE.Mesh(earGeo, darkMat);
      earR.position.set(0.3, 0.25, 0);
      earR.scale.set(0.9, 0.5, 0.7);
      this.headGroup.add(earR);
      this.ears.push(earR);

      // 面部
      this.faceGroup = new THREE.Group();
      this.faceGroup.position.z = 0.3;

      // 眼白
      const eyeGeo = new THREE.SphereGeometry(0.1, 16, 16);
      const eyeL = new THREE.Mesh(eyeGeo, whiteMat);
      eyeL.position.set(-0.14, 0.06, 0.05);
      this.faceGroup.add(eyeL);

      const eyeR = new THREE.Mesh(eyeGeo, whiteMat);
      eyeR.position.set(0.14, 0.06, 0.05);
      this.faceGroup.add(eyeR);

      // 瞳孔
      const pupilGeo = new THREE.SphereGeometry(0.055, 12, 12);
      const pupilL = new THREE.Mesh(pupilGeo, pupilMat);
      pupilL.position.set(-0.14, 0.04, 0.12);
      this.faceGroup.add(pupilL);

      const pupilR = new THREE.Mesh(pupilGeo, pupilMat);
      pupilR.position.set(0.14, 0.04, 0.12);
      this.faceGroup.add(pupilR);

      // 眼睛高光
      const highlightMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.3 });
      const hlGeo = new THREE.SphereGeometry(0.025, 8, 8);
      const hlL = new THREE.Mesh(hlGeo, highlightMat);
      hlL.position.set(-0.16, 0.08, 0.14);
      this.faceGroup.add(hlL);

      const hlR = new THREE.Mesh(hlGeo, highlightMat);
      hlR.position.set(0.12, 0.08, 0.14);
      this.faceGroup.add(hlR);

      // 鼻子
      const nose = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), noseMat);
      nose.position.set(0, -0.02, 0.1);
      nose.scale.set(1, 0.7, 0.8);
      this.faceGroup.add(nose);

      // 嘴巴 (可动)
      this.mouth = new THREE.Mesh(
        new THREE.TorusGeometry(0.035, 0.008, 6, 12, Math.PI),
        new THREE.MeshStandardMaterial({ color: 0x444444 })
      );
      this.mouth.position.set(0, -0.08, 0.1);
      this.mouth.rotation.x = 0.2;
      this.mouth.rotation.z = 0.1;
      this.faceGroup.add(this.mouth);

      // 腮红
      this.blushL = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 8), pinkMat);
      this.blushL.position.set(-0.2, -0.04, 0.02);
      this.blushL.scale.set(1.2, 0.6, 0.5);
      this.faceGroup.add(this.blushL);

      this.blushR = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 8), pinkMat);
      this.blushR.position.set(0.2, -0.04, 0.02);
      this.blushR.scale.set(1.2, 0.6, 0.5);
      this.faceGroup.add(this.blushR);

      this.headGroup.add(this.faceGroup);
      this.panda.add(this.headGroup);

      // ----- 手臂 -----
      const armGeo = new THREE.SphereGeometry(0.1, 10, 10);
      const armMat = darkMat;

      const armL = new THREE.Mesh(armGeo, armMat);
      armL.position.set(-0.45, 0.0, 0.1);
      armL.scale.set(0.6, 1.2, 0.7);
      armL.castShadow = true;
      this.bodyGroup.add(armL);
      this.arms = [{ mesh: armL, basePos: new THREE.Vector3(-0.45, 0.0, 0.1) }];

      const armR = new THREE.Mesh(armGeo, armMat);
      armR.position.set(0.45, 0.0, 0.1);
      armR.scale.set(0.6, 1.2, 0.7);
      armR.castShadow = true;
      this.bodyGroup.add(armR);
      this.arms.push({ mesh: armR, basePos: new THREE.Vector3(0.45, 0.0, 0.1) });

      // 尾巴
      const tail = new THREE.Mesh(
        new THREE.SphereGeometry(0.06, 8, 8),
        new THREE.MeshStandardMaterial({ color: 0xeeeeee })
      );
      tail.position.set(0, -0.1, -0.4);
      this.bodyGroup.add(tail);

      this.panda.position.y = 0.25;
      this.scene.add(this.panda);

      // 配饰
      this._setAccessory(cfg.accessory);
    }

    _setAccessory(type) {
      if (this.currentAccessory) {
        this.headGroup.remove(this.currentAccessory);
        this.currentAccessory = null;
      }
      if (type === 'none') return;

      let mesh = null;
      if (type === 'bow') {
        // 蝴蝶结
        const bowGroup = new THREE.Group();
        const bowMat = new THREE.MeshStandardMaterial({ color: 0xff6699 });
        const wing1 = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.04, 6), bowMat);
        wing1.rotation.z = 0.3;
        wing1.position.set(-0.07, 0, 0);
        bowGroup.add(wing1);
        const wing2 = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.04, 6), bowMat);
        wing2.rotation.z = -0.3;
        wing2.position.set(0.07, 0, 0);
        bowGroup.add(wing2);
        const center = new THREE.Mesh(new THREE.SphereGeometry(0.02, 6, 6), bowMat);
        bowGroup.add(center);
        bowGroup.position.set(0, 0.4, 0.15);
        mesh = bowGroup;
      } else if (type === 'scarf') {
        // 围巾
        const scarfMat = new THREE.MeshStandardMaterial({ color: 0x88ccff });
        const scarf = new THREE.Mesh(new THREE.TorusGeometry(0.25, 0.04, 8, 16), scarfMat);
        scarf.position.set(0, 0.05, 0.1);
        scarf.rotation.x = 0.3;
        scarf.scale.set(1, 0.5, 0.6);
        mesh = scarf;
      } else if (type === 'bamboo') {
        // 竹子（拿在手里）
        const bambooGroup = new THREE.Group();
        const stickMat = new THREE.MeshStandardMaterial({ color: 0x6aaa5a });
        const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.02, 0.4, 6), stickMat);
        stick.position.set(0, 0, 0);
        bambooGroup.add(stick);
        const leafMat = new THREE.MeshStandardMaterial({ color: 0x4caf50 });
        const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.04, 4, 4), leafMat);
        leaf.position.set(0, 0.22, 0);
        leaf.scale.set(1, 0.3, 1);
        bambooGroup.add(leaf);
        bambooGroup.position.set(0.45, -0.1, 0.25);
        bambooGroup.rotation.z = 0.3;
        mesh = bambooGroup;
      }

      if (mesh) {
        this.currentAccessory = mesh;
        this.headGroup.add(mesh);
      }
    }

    // ========== 动画控制 ==========
    setEmotion(emotion) {
      this.animState = emotion;
    }

    setAccessory(type) {
      this.config.accessory = type;
      this._setAccessory(type);
    }

    setFurColor(color) {
      this.config.furColor = color;
      this.panda.children.forEach(child => {
        child.traverse(node => {
          if (node.isMesh && node.material.color && node.material.color.getHex() === 0xffffff) {
            node.material.color.setHex(color);
          }
        });
      });
    }

    setSceneBg(type) {
      this.config.sceneBg = type;
      // 简单移除旧地面装饰重新添加
      while (this.scene.children.length > 3) {
        const child = this.scene.children[this.scene.children.length - 1];
        if (child !== this.panda && child.type === 'Mesh') {
          this.scene.remove(child);
        } else break;
      }
      this._buildScene();
    }

    // ========== 渲染循环 ==========
    _animate() {
      const loop = () => {
        requestAnimationFrame(loop);
        this.clock += 0.016;
        this._updateAnim();
        this.renderer.render(this.scene, this.camera);
      };
      loop();
    }

    _updateAnim() {
      if (!this.panda) return;
      const t = this.clock;
      const speed = 1.0;

      switch (this.animState) {
        case 'idle':
          // 呼吸: 身体轻微上下 + 耳朵轻晃
          this.bodyGroup.position.y = Math.sin(t * 1.5) * 0.008;
          this.headGroup.rotation.z = Math.sin(t * 0.8) * 0.02;
          this.ears.forEach((e, i) => {
            e.rotation.z = Math.sin(t * 1.2 + i) * 0.03;
          });
          this.mouth.scale.x = 1;
          this.mouth.scale.y = 1;
          break;

        case 'talking':
          // 嘴巴开合 + 头轻点
          const mouthOpen = Math.abs(Math.sin(t * 12)) * 0.3 + 0.7;
          this.mouth.scale.x = mouthOpen;
          this.mouth.scale.y = mouthOpen * 0.5;
          this.headGroup.rotation.x = Math.sin(t * 3) * 0.03;
          this.bodyGroup.position.y = Math.sin(t * 1.5) * 0.008;
          break;

        case 'happy':
          // 开心蹦跳 + 转圈
          this.bodyGroup.position.y = Math.abs(Math.sin(t * 3)) * 0.05;
          this.panda.rotation.y = Math.sin(t * 1.5) * 0.2;
          this.headGroup.rotation.z = Math.sin(t * 2) * 0.05;
          this.ears.forEach(e => {
            e.rotation.z = Math.sin(t * 2) * 0.06;
          });
          // 腮红变亮
          if (this.blushL) {
            this.blushL.material.opacity = 0.5 + Math.sin(t * 2) * 0.2;
            this.blushR.material.opacity = 0.5 + Math.sin(t * 2) * 0.2;
          }
          break;

        case 'sad':
          // 低头 + 耳朵垂
          this.headGroup.rotation.x = 0.15;
          this.bodyGroup.position.y = Math.sin(t * 1) * 0.005 - 0.01;
          this.ears.forEach(e => {
            e.rotation.z = 0.08;
          });
          this.mouth.scale.x = 0.8;
          this.mouth.scale.y = 0.6;
          break;

        case 'wave':
          // 挥手
          if (this.arms.length > 0) {
            const arm = this.arms[0];
            arm.mesh.position.x = arm.basePos.x + Math.sin(t * 4) * 0.05;
            arm.mesh.position.y = arm.basePos.y + Math.sin(t * 4) * 0.08;
          }
          this.headGroup.rotation.z = Math.sin(t * 2) * 0.04;
          break;
      }
    }

    _handleResize() {
      const resizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width, height } = entry.contentRect;
          this.camera.aspect = width / height;
          this.camera.updateProjectionMatrix();
          this.renderer.setSize(width, height);
        }
      });
      resizeObserver.observe(this.container);
    }

    // 销毁
    dispose() {
      this.renderer.dispose();
      if (this.container.contains(this.renderer.domElement)) {
        this.container.removeChild(this.renderer.domElement);
      }
    }
  }

  // ========== 导出 ==========
  global.Panda3D = Panda3D;

})(typeof window !== 'undefined' ? window : this);