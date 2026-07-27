// Cyberpunk Dashboard — JS for SSE progress, debug, clean-db, select-all
(function () {
    'use strict';

    // =========================================================================
    // Dino Runner — Chrome Dino-style animation using real Chromium sprites
    // Sprite sheet: BSD-licensed, extracted from Chromium error page
    // =========================================================================

    var dinoSprite = new Image();
    dinoSprite.src = '/static/offline-sprite.png';

    // Sprite positions (1x, from Chromium runner source)
    var TX = 848, TY = 2, TW = 44, TH = 47;
    var CS_X = 228, CS_W = 17, CS_H = 35;
    var CL_X = 332, CL_W = 25, CL_H = 50;
    var PT_X = 134, PT_W = 46, PT_H = 40;
    var DINO_FRAMES = {
        RUNNING: [88, 132],
        JUMPING: [0],
        DUCKING: [264, 323]
    };

    function DinoCanvasRenderer(canvas, container) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.container = container;
        this.running = false;
        this.currentPct = 0;
        this.targetPct = 0;
        this.frameIdx = 0;
        this.lastTime = 0;
        this.animId = null;
        this.obstacles = [];
        this.clouds = [];
        this.isJumping = false;
        this.jumpStart = 0;
        this.isDucking = false;
        this.duckStart = 0;
        this.pteroFrame = 0;
        this.pteroLast = 0;
        this.lastObsSpawn = 0;
        this.lastCloudSpawn = 0;
        this.done = false;
        this.success = false;
        this.GY = 0;
        this.dinoX = 40;
        this.score = 0;
        this.hiScore = parseInt(localStorage.getItem('dino-hi-score') || '0', 10);
        this._readThemeColors();
        this.resize();
        this._boundLoop = this._loop.bind(this);
    }

    DinoCanvasRenderer.prototype._readThemeColors = function () {
        var style = getComputedStyle(this.container);
        this.accentColor = style.getPropertyValue('--accent').trim() || '#5f87ff';
    };

    DinoCanvasRenderer.prototype.resize = function () {
        var w = this.container.offsetWidth || 1200;
        var h = this.container.offsetHeight || 160;
        var dpr = window.devicePixelRatio || 1;
        this.canvas.width = Math.max(1, Math.round(w * dpr));
        this.canvas.height = Math.max(1, Math.round(h * dpr));
        this.canvas.style.width = w + 'px';
        this.canvas.style.height = h + 'px';
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        this.GY = h;
        this.canvasWidth = w;
        this.canvasHeight = h;
        this.moonX = w - 70; // moon position
    };

    DinoCanvasRenderer.prototype.updateProgress = function (pct) {
        this.targetPct = pct;
    };

    DinoCanvasRenderer.prototype.start = function () {
        if (this.running) return;
        this.running = true;
        this.currentPct = 0;
        this.targetPct = 0;
        this.frameIdx = 0;
        this.lastTime = 0;
        this.pteroFrame = 0;
        this.pteroLast = 0;
        this.isJumping = false;
        this.isDucking = false;
        this.obstacles = [];
        this.clouds = [];
        this.lastObsSpawn = Date.now();
        this.lastCloudSpawn = Date.now();
        this.done = false;
        this.success = false;
        this._readThemeColors();
        this.resize();
        this.canvas.style.display = 'block';
        this.animId = requestAnimationFrame(this._boundLoop);
    };

    DinoCanvasRenderer.prototype.stop = function (wasSuccess) {
        this.running = false;
        if (this.animId) {
            cancelAnimationFrame(this.animId);
            this.animId = null;
        }
        this.done = true;
        this.success = wasSuccess;
        this.drawScene();
    };

    DinoCanvasRenderer.prototype.spawnObstacle = function () {
        var r = Math.random();
        var type = r < 0.35 ? 'cs' : r < 0.65 ? 'cl' : 'pt';
        this.obstacles.push({ type: type, x: this.canvasWidth + 100, frame: 0 });
    };

    DinoCanvasRenderer.prototype.spawnCloud = function () {
        this.clouds.push({
            x: this.canvasWidth + 100,
            y: Math.random() * this.GY * 0.12 + 8
        });
    };

    DinoCanvasRenderer.prototype.checkAutoActions = function () {
        var dinoRight = this.dinoX + TW;
        for (var i = 0; i < this.obstacles.length; i++) {
            var o = this.obstacles[i];
            var dist = o.x - dinoRight;
            if (o.type === 'pt' && dist < 40 && dist > -15 && !this.isJumping) {
                this.isDucking = true;
                this.duckStart = Date.now();
                return;
            }
            if (dist < 30 && dist > -15 && !this.isJumping && !this.isDucking) {
                this.isJumping = true;
                this.jumpStart = Date.now();
                return;
            }
        }
        if (this.isDucking && Date.now() - this.duckStart > 500) {
            this.isDucking = false;
        }
    };

    DinoCanvasRenderer.prototype.drawScene = function () {
        if (!dinoSprite.complete || dinoSprite.naturalWidth === 0) return;
        var w = this.canvasWidth;
        var h = this.canvasHeight;
        var ctx = this.ctx;
        var isLight = document.documentElement.getAttribute('data-theme') === 'light';
        ctx.clearRect(0, 0, w, h);
        ctx.imageSmoothingEnabled = false;
        var color = this.accentColor;

        // Ground — colored line using accent color (visible in both themes)
        ctx.fillStyle = color;
        ctx.fillRect(0, this.GY - 3, w, 2);

        // Moon (dark mode only)
        if (!isLight) {
            ctx.drawImage(dinoSprite, 484, 2, 46, 46, this.canvasWidth - 70, 8, 46, 46);
        }

        // Stars (dark mode only, subtle)
        if (!isLight) {
            ctx.drawImage(dinoSprite, 645, 2, 30, 20, this.canvasWidth - 120, 18, 30, 20);
        }

        // Clouds — draw from sprite sheet, invert in light mode
        if (isLight) ctx.filter = 'invert(1)';
        for (var i = 0; i < this.clouds.length; i++) {
            var cl = this.clouds[i];
            ctx.drawImage(dinoSprite, 86, 2, 46, 16,
                cl.x, cl.y, 46 * 0.5, 16 * 0.5);
        }
        ctx.filter = 'none';

        // Obstacles
        for (var i = 0; i < this.obstacles.length; i++) {
            var o = this.obstacles[i];
            var sx, sw, sh;
            if (o.type === 'cs') { sx = CS_X; sw = CS_W; sh = CS_H; }
            else if (o.type === 'cl') { sx = CL_X; sw = CL_W; sh = CL_H; }
            else { sx = PT_X + (o.frame || 0) * PT_W; sw = PT_W; sh = PT_H; }
            var ow = sw, oh = sh;
            var oy = o.type === 'pt' ? this.GY - oh - 30 : this.GY - oh;
            ctx.drawImage(dinoSprite, sx, 2, sw, sh, o.x, oy, ow, oh);
        }

        // Dino
        var ssx, ssy = 2, ssw, ssh, dw, dh, dy;

        if (this.isDucking) {
            ssx = TX + DINO_FRAMES.DUCKING[this.frameIdx % 2];
            ssw = 59; ssh = 47;
            dw = 59; dh = 47;
            dy = this.GY - dh;
            if (Date.now() - this.duckStart > 500) this.isDucking = false;
        } else if (this.isJumping) {
            ssx = TX + DINO_FRAMES.JUMPING[0];
            ssw = TW; ssh = TH;
            dw = TW; dh = TH;
            dy = this.GY - dh;
            var el = Date.now() - this.jumpStart, dur = 520;
            if (el >= dur) { this.isJumping = false; }
            else { dy = this.GY - dh - 55 * Math.sin((el / dur) * Math.PI); }
        } else {
            ssx = TX + DINO_FRAMES.RUNNING[this.frameIdx % 2];
            ssw = TW; ssh = TH;
            dw = TW; dh = TH;
            dy = this.GY - dh;
        }

        ctx.drawImage(dinoSprite, ssx, ssy, ssw, ssh, this.dinoX, dy, dw, dh);
    };

    DinoCanvasRenderer.prototype._loop = function (timestamp) {
        if (!this.running) return;

        // Interpolate progress
        var diff = this.targetPct - this.currentPct;
        if (Math.abs(diff) > 0.5) {
            this.currentPct += diff * 0.15;
        } else {
            this.currentPct = this.targetPct;
        }

        // Frame animation
        if (!this.lastTime) this.lastTime = timestamp;
        if (timestamp - this.lastTime > 130) { this.frameIdx++; this.lastTime = timestamp; }

        // Pterodactyl wing flap
        if (timestamp - this.pteroLast > 200) {
            this.pteroFrame = 1 - this.pteroFrame;
            this.pteroLast = timestamp;
            for (var i = 0; i < this.obstacles.length; i++) {
                if (this.obstacles[i].type === 'pt') this.obstacles[i].frame = this.pteroFrame;
            }
        }

        // Spawn obstacles
        if (Date.now() - this.lastObsSpawn > 1800 + Math.random() * 1200) {
            this.spawnObstacle();
            this.lastObsSpawn = Date.now();
        }
        if (Date.now() - this.lastCloudSpawn > 4000 + Math.random() * 2000) {
            this.spawnCloud();
            this.lastCloudSpawn = Date.now();
        }

        // Move obstacles and clouds
        var speed = 4 + (this.targetPct / 100) * 3;

        // Update score (only while running and not ducking/jumping)
        if (this.running && !this.isDucking && !this.isJumping) {
            this.score += Math.ceil(speed * 0.1);
            if (this.score > this.hiScore) {
                this.hiScore = this.score;
                localStorage.setItem('dino-hi-score', this.hiScore);
            }
        }
        for (var i = this.obstacles.length - 1; i >= 0; i--) {
            this.obstacles[i].x -= speed * 0.7;
            if (this.obstacles[i].x < -200) this.obstacles.splice(i, 1);
        }
        for (var i = this.clouds.length - 1; i >= 0; i--) {
            this.clouds[i].x -= speed * 0.2;
            if (this.clouds[i].x < -200) this.clouds.splice(i, 1);
        }

        this.checkAutoActions();
        this.drawScene();

        this.animId = requestAnimationFrame(this._boundLoop);
    };
    // =========================================================================
    // SSE Scan Progress — updated with Dino integration
    // =========================================================================

    var eventSource = null;
    var dinoRenderer = null;

    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/scan') {
            startScanListener();
        }
    });

    function getScanButton() {
        return document.querySelector('.btn-scan');
    }

    function disableScanButton() {
        var btn = getScanButton();
        if (btn) {
            btn.disabled = true;
            btn.classList.add('btn-scan-disabled');
        }
    }

    function enableScanButton() {
        var btn = getScanButton();
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('btn-scan-disabled');
        }
        // Hide STOP button in header when scan stops
        var stopBtn = document.getElementById('stop-btn');
        if (stopBtn) stopBtn.style.display = 'none';
    }

    function updateProgress(data) {
        var fill = document.querySelector('.scan-progress .progress-fill');
        if (fill && typeof data.pct !== 'undefined') {
            fill.style.width = Math.round(data.pct) + '%';
        }
        // Also update dino renderer
        if (dinoRenderer) {
            dinoRenderer.updateProgress(data.pct);
        }
    }

    function showDone(data) {
        var wrap = document.getElementById('scan-progress');
        if (!wrap) return;

        if (data.error) {
            wrap.innerHTML = '<div class="progress-track"><div class="progress-fill" style="width:100%"></div></div>';
            wrap.className = 'scan-progress scan-progress-error';
        } else {
            wrap.innerHTML = '<div class="progress-track"><div class="progress-fill" style="width:100%"></div></div>';
            wrap.className = 'scan-progress scan-progress-done';
        }

        // Dino renderer cleanup
        dinoRenderer = null;

        // Refresh the table — hx-trigger="load" is an internal HTMX mechanism
        // that does NOT respond to htmx.trigger(). Use explicit ajax() instead.
        var tableContainer = document.getElementById('table-container');
        if (tableContainer) {
            htmx.ajax('GET', '/table', {target: '#table-container', swap: 'innerHTML'});
        }

        // Re-enable the scan button
        enableScanButton();
    }

    function startScanListener() {
        if (eventSource) {
            eventSource.close();
        }
        eventSource = new EventSource('/scan/status');

        // Disable scan button while running
        disableScanButton();

        // Show STOP button in SCAN tab (always visible when scan runs)
        var stopBtn = document.getElementById('stop-btn');
        if (stopBtn) {
            stopBtn.style.display = 'inline-block';
        }

        // Expand the dino banner and init dino renderer.
        // Use htmx:afterSettle (not requestAnimationFrame alone) so that HTMX
        // has already removed its htmx-added class before we touch the element.
        // Re-query the DOM inside the callback — never trust a closure over
        // an element that HTMX may swap asynchronously.
        var settleHandler = function () {
            document.body.removeEventListener('htmx:afterSettle', settleHandler);
            var dinoBanner = document.getElementById('dino-banner');
            if (dinoBanner) {
                // Single rAF to let the CSS transition kick off after the
                // class is added in the same frame.
                requestAnimationFrame(function () {
                    dinoBanner.classList.add('expanded');
                    var canvas = document.getElementById('dino-canvas');
                    if (canvas) {
                        dinoRenderer = new DinoCanvasRenderer(canvas, dinoBanner);
                        dinoRenderer.start();
                    }
                });
            }
        };
        document.body.addEventListener('htmx:afterSettle', settleHandler);

        eventSource.onmessage = function (e) {
            try {
                var data = JSON.parse(e.data);
                if (data.done) {
                    eventSource.close();
                    eventSource = null;

                    // Stop dino renderer — freezes final pose on canvas
                    var wasSuccess = !data.error;
                    if (dinoRenderer) {
                        dinoRenderer.stop(wasSuccess);
                    }

                    // Phase 1: let user see the final pose for 1.5s
                    // Phase 2: collapse the banner (remove expanded → CSS transition to 0)
                    // Phase 3: after collapse transition, show done bar
                    setTimeout(function () {
                        var banner = document.getElementById('dino-banner');
                        if (banner) {
                            banner.classList.remove('expanded');
                        }
                        // Wait for CSS transition (300ms) then show done bar
                        setTimeout(function () {
                            showDone(data);
                        }, 350);
                    }, 1500);
                } else {
                    updateProgress(data);
                    // Append log lines to the log viewer
                    if (data.log) {
                        var logEl = document.getElementById('scan-log');
                        if (logEl) {
                            logEl.textContent += data.log + '\n';
                            logEl.scrollTop = logEl.scrollHeight;
                        }
                    }
                }
            } catch (err) {
                console.error('SSE parse error:', err);
            }
        };

        eventSource.onerror = function () {
            console.warn('SSE connection error, will retry...');
            // Re-enable after timeout in case SSE never comes back
            setTimeout(function () {
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                enableScanButton();
            }, 10000);
        };
    }

    // -- Settings: Debug Mode -------------------------------------------------

    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.id === 'settings-debug') {
            localStorage.setItem('dashboard-debug', e.target.checked ? 'on' : 'off');
            console.log('[Debug] Debug mode ' + (e.target.checked ? 'ON' : 'OFF') + ' — limiting to 3 results per scraper.');
        }
    });

// After clean-db, hide CLEAN DB and STOP buttons
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/clean-db') {
            // Stop scan if running (server stops it)
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            enableScanButton();
            var progressSection = document.getElementById('scan-progress-section');
            if (progressSection) {
                progressSection.innerHTML = '';
            }
            dinoRenderer = null;

            // Hide STOP button in SCAN tab
            var stopBtn = document.getElementById('stop-btn');
            if (stopBtn) stopBtn.style.display = 'none';
        }
    });

    // After /scan/stop, close SSE, re-enable SCAN, clear progress, kill dino
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/scan/stop') {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            enableScanButton();
            var progressSection = document.getElementById('scan-progress-section');
            if (progressSection) {
                progressSection.innerHTML = '';
            }
            dinoRenderer = null;

            // Hide STOP button in SCAN tab
            var stopBtn = document.getElementById('stop-btn');
            if (stopBtn) stopBtn.style.display = 'none';
        }
    });

    // -- Settings: Theme ---------------------------------------------------

    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.id === 'settings-theme') {
            var theme = e.target.value;
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('dashboard-theme', theme);
        }
    });

    // -- Settings: Font Size -----------------------------------------------

    document.body.addEventListener('input', function (e) {
        if (e.target && e.target.id === 'settings-font-size') {
            var size = e.target.value + 'px';
            document.documentElement.style.fontSize = size;
            localStorage.setItem('dashboard-font-size', size);
            var valDisplay = document.getElementById('font-size-value');
            if (valDisplay) valDisplay.textContent = size;
        }
    });

    // -- Settings: Font Family ---------------------------------------------

    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.id === 'settings-font-family') {
            var family = e.target.value;
            document.documentElement.style.setProperty('--font-mono', family);
            localStorage.setItem('dashboard-font-family', family);
        }
    });

    // -- Settings: Animations ----------------------------------------------

    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.id === 'settings-animations') {
            localStorage.setItem('dashboard-animations', e.target.checked ? 'on' : 'off');
        }
    });

    // -- Settings: Compact Mode --------------------------------------------

    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.id === 'settings-compact') {
            if (e.target.checked) {
                document.body.classList.add('compact-mode');
            } else {
                document.body.classList.remove('compact-mode');
            }
            localStorage.setItem('dashboard-compact', e.target.checked ? 'on' : 'off');
        }
    });

    // -- Load saved settings on page load ----------------------------------
    // Note: sort config is loaded inline in settings.html via loadSortConfig()

    (function loadSettings() {
        var savedTheme = localStorage.getItem('dashboard-theme');
        if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

        var savedFontSize = localStorage.getItem('dashboard-font-size');
        if (savedFontSize) document.documentElement.style.fontSize = savedFontSize;

        var savedFontFamily = localStorage.getItem('dashboard-font-family');
        if (savedFontFamily) document.documentElement.style.setProperty('--font-mono', savedFontFamily);

        var savedCompact = localStorage.getItem('dashboard-compact');
        if (savedCompact === 'on') document.body.classList.add('compact-mode');
    })();

    // -- DATA Button Toggle ----------------------------------------------

    var dataBtn = document.getElementById('data-btn');
    var dataActive = false;
    var savedTableContent = null;

    if (dataBtn) {
        dataBtn.addEventListener('click', function () {
            dataActive = !dataActive;
            var mc = document.getElementById('main-content');
            if (!mc) return;

if (dataActive) {
                    // Save table, swap to panel
                    savedTableContent = mc.innerHTML;
                    this.textContent = 'TABLE';
                    this.classList.add('btn-data-active');
                    htmx.ajax('GET', '/datos/panel', {target: '#main-content', swap: 'innerHTML'});
                } else {
                    // Restore table
                    this.classList.remove('btn-data-active');
                    this.textContent = 'DATA';
                    mc.innerHTML = savedTableContent;
                    htmx.ajax('GET', '/table', {target: '#table-container', swap: 'innerHTML'});
                }
        });
    }

    // -- HTMX Event Handlers for Datos Panel -----------------------------

    // Before SAVE: disable button to prevent double-click
    document.body.addEventListener('htmx:beforeRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/datos/fields/save') {
            var btn = document.querySelector('.btn-scan');
            if (btn) btn.disabled = true;
        }
        if (evt.detail.pathInfo.requestPath === '/datos/fields/add') {
            var btn = document.querySelector('.btn-add-field');
            if (btn) btn.disabled = true;
        }
    });

    // After SAVE completes: log status message, re-enable button
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/datos/fields/save') {
            var btn = document.querySelector('.btn-scan');
            if (btn) btn.disabled = false;
            if (evt.detail.successful) {
                console.log('[Datos] Fields saved successfully.');
            } else {
                console.error('[Datos] Save failed.');
            }
        }
    });

    // After ADD FIELD: re-enable button, ensure the new row is visible
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/datos/fields/add') {
            var btn = document.querySelector('.btn-add-field');
            if (btn) btn.disabled = false;
        }
    });

    // After CV upload: refresh the CV section
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo && (
            evt.detail.pathInfo.requestPath === '/datos/cv/upload' ||
            evt.detail.pathInfo.requestPath === '/datos/cv/delete'
        )) {
            // The HTMX response already swaps the cv-section
            console.log('[Datos] CV updated.');
        }
    });

    // After platform add/remove: refresh the platform list
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo && (
            evt.detail.pathInfo.requestPath === '/datos/platforms/add' ||
            evt.detail.pathInfo.requestPath.indexOf('/datos/platforms/remove/') !== -1
        )) {
            console.log('[Datos] Platform list updated.');
        }
    });

    // -- SELECT Button Toggle — REMOVED per user request ----------------------
    // SELECT button and checkbox column have been removed.
    // document.body.addEventListener('click', function (e) { ... });

    // Event delegation for checkbox changes (survives HTMX swaps)
    // REMOVED: SELECT/checkbox column removed per user request.
    // document.body.addEventListener('change', function (e) { ... });

    // After clean-db: re-enable TABLE view
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/clean-db') {
            // If DATA panel is active, go back to table view
            if (dataActive) {
                var mc = document.getElementById('main-content');
                if (mc && savedTableContent) {
                    mc.innerHTML = savedTableContent;
                }
                var btn = document.getElementById('data-btn');
                if (btn) {
                    btn.classList.remove('btn-data-active');
                    btn.textContent = 'DATA';
                }
                dataActive = false;
            }
        }
    });

// -- Tab Navigation: active state management ---------------------------

    // Track the last clicked tab via data-tab attribute
    var lastTabAttr = 'status';

    document.body.addEventListener('htmx:beforeRequest', function(evt) {
        var trigger = evt.detail.elt;
        if (trigger?.dataset?.tab) {
            lastTabAttr = trigger.dataset.tab;
        }
    });

    document.body.addEventListener('htmx:afterSwap', function(evt) {
        if (evt.detail.target?.id === 'main-content') {
            document.querySelectorAll('.tab').forEach(function(t) {
                t.classList.remove('tab-active');
            });
            var tab = document.querySelector('[data-tab="' + lastTabAttr + '"]');
            if (tab) tab.classList.add('tab-active');
        }
    });

    // -- SCAN restore saved params after tab load -------------------------

    document.body.addEventListener('htmx:afterSwap', function(evt) {
        if (evt.detail.target?.id !== 'main-content') return;
        var scanTab = document.getElementById('scan-tab');
        if (!scanTab) return;
        // Params are already set by server from saved JSON, no client action needed
    });

})();

// -- Filter Dropdown (event delegation — survives HTMX swaps) ---------------

(function () {
    'use strict';

    // Toggle dropdown on button click (event delegation on body)
    document.body.addEventListener('click', function (e) {
        var btn = e.target.closest('#filter-btn');
        if (btn) {
            e.stopPropagation();
            var menu = document.getElementById('filter-menu');
            if (menu) {
                var isVisible = menu.style.display !== 'none';
                menu.style.display = isVisible ? 'none' : 'block';
            }
        }
    });

    // Close dropdown when clicking outside
    document.body.addEventListener('click', function (e) {
        var wrapper = document.getElementById('filter-wrapper');
        if (wrapper && !wrapper.contains(e.target)) {
            var menu = document.getElementById('filter-menu');
            if (menu) menu.style.display = 'none';
        }
    });

    // Refresh table when any filter checkbox changes
    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.classList.contains('filter-checkbox')) {
            var checkboxes = document.querySelectorAll('.filter-checkbox:checked');
            var activeKeys = [];
            for (var i = 0; i < checkboxes.length; i++) {
                activeKeys.push(checkboxes[i].getAttribute('data-filter-key'));
            }
            var filtersParam = activeKeys.join(',');

            // Update hidden filter-state input for HTMX includes
            var filterState = document.getElementById('filter-state');
            if (filterState) filterState.value = filtersParam;

            var search = document.getElementById('search-input');
            var since = document.querySelector('[name="since"]');
            var params = 'filters=' + encodeURIComponent(filtersParam);
            if (search && search.value) {
                params += '&search=' + encodeURIComponent(search.value);
            }
            if (since) {
                params += '&since=' + encodeURIComponent(since.value);
            }
            htmx.ajax('GET', '/table?' + params, {
                target: '#table-container',
                swap: 'innerHTML'
            });
        }
    });

    // Refresh table when date filter changes
    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.name === 'since') {
            var params = 'since=' + encodeURIComponent(e.target.value);
            var search = document.getElementById('search-input');
            if (search && search.value) {
                params += '&search=' + encodeURIComponent(search.value);
            }
            var filterState = document.getElementById('filter-state');
            if (filterState && filterState.value) {
                params += '&filters=' + encodeURIComponent(filterState.value);
            }
            var perPage = document.querySelector('[name="per_page"]');
            if (perPage) {
                params += '&per_page=' + encodeURIComponent(perPage.value);
            }
            htmx.ajax('GET', '/table?' + params, {
                target: '#table-container',
                swap: 'innerHTML'
            });
        }
    });

})();

// -- Settings: Sort Config ---------------------------------------------------
// Note: sort config is loaded inline in settings.html via loadSortConfig()

var SORT_COLUMNS = [
    'date_published', 'platform', 'title', 'company',
    'modality', 'salary', 'location', 'status'
];

function getSortConfig() {
    var raw = localStorage.getItem('fb-sort-config');
    if (!raw) return [];
    try { return JSON.parse(raw); } catch (e) { return []; }
}

function saveSortConfig() {
    var container = document.getElementById('sort-config-container');
    if (!container) return;
    var rows = container.querySelectorAll('.sort-level');
    var config = [];
    for (var i = 0; i < rows.length; i++) {
        var col = rows[i].querySelector('.sort-col-select').value;
        var dir = rows[i].querySelector('.sort-dir-select').value;
        config.push({col: col, dir: dir});
    }
    if (config.length === 0) {
        localStorage.removeItem('fb-sort-config');
    } else {
        localStorage.setItem('fb-sort-config', JSON.stringify(config));
    }
}

function addSortLevel(col, dir) {
    var container = document.getElementById('sort-config-container');
    if (!container) return;

    var row = document.createElement('div');
    row.className = 'settings-row sort-level';

    // Column select
    var colSelect = document.createElement('select');
    colSelect.className = 'sort-col-select settings-select';
    for (var i = 0; i < SORT_COLUMNS.length; i++) {
        var opt = document.createElement('option');
        opt.value = SORT_COLUMNS[i];
        opt.textContent = SORT_COLUMNS[i];
        if (SORT_COLUMNS[i] === col) opt.selected = true;
        colSelect.appendChild(opt);
    }
    colSelect.addEventListener('change', saveSortConfig);

    // Direction select
    var dirSelect = document.createElement('select');
    dirSelect.className = 'sort-dir-select settings-select';
    var dirs = ['desc', 'asc'];
    for (var i = 0; i < dirs.length; i++) {
        var opt = document.createElement('option');
        opt.value = dirs[i];
        opt.textContent = dirs[i];
        if (dirs[i] === dir) opt.selected = true;
        dirSelect.appendChild(opt);
    }
    dirSelect.addEventListener('change', saveSortConfig);

    // Remove button
    var removeBtn = document.createElement('button');
    removeBtn.className = 'sort-remove-btn';
    removeBtn.textContent = '\u00d7';
    removeBtn.setAttribute('type', 'button');
    removeBtn.setAttribute('title', 'Remove sort level');
    removeBtn.onclick = function () { removeSortLevel(this); };

    row.appendChild(colSelect);
    row.appendChild(dirSelect);
    row.appendChild(removeBtn);
    container.appendChild(row);

    return row;
}

function removeSortLevel(btn) {
    var row = btn.closest('.sort-level');
    if (!row) return;
    row.parentNode.removeChild(row);

    // If no rows left, add a default one
    var container = document.getElementById('sort-config-container');
    if (container && container.querySelectorAll('.sort-level').length === 0) {
        addSortLevel('date_published', 'desc');
    }
    saveSortConfig();
}

function loadSortConfig() {
    var config = getSortConfig();
    if (config.length === 0) {
        addSortLevel('date_published', 'desc');
    } else {
        for (var i = 0; i < config.length; i++) {
            addSortLevel(config[i].col, config[i].dir);
        }
    }
}

// -- Status Management: clickable badges to mark jobs as postulado ----------

function toggleStatusMenu(el) {
    // Close any other open status menus
    document.querySelectorAll('.status-menu').forEach(function(m) {
        if (m !== el.nextElementSibling) {
            m.style.display = 'none';
            m.style.position = '';  // restore default
        }
    });
    var menu = el.nextElementSibling;
    if (menu && menu.classList.contains('status-menu')) {
        var isOpening = menu.style.display === 'none' || (menu.style.display !== 'block' && getComputedStyle(menu).display === 'none');
        menu.style.display = isOpening ? 'block' : 'none';
        if (isOpening) {
            // Switch to position:fixed to escape .table-responsive overflow clipping
            menu.style.position = 'fixed';
            menu.style.top = '';
            menu.style.bottom = '';
            menu.style.left = '';
            menu.style.right = '';

            // Get badge viewport position
            var badgeRect = el.getBoundingClientRect();
            var vw = window.innerWidth;
            var vh = window.innerHeight;

            // Position menu below badge, aligned left
            var menuTop = badgeRect.bottom + 2;
            var menuLeft = badgeRect.left;

            // Force layout so getBoundingClientRect is accurate with the new fixed position
            menu.style.top = menuTop + 'px';
            menu.style.left = menuLeft + 'px';
            menu.style.right = 'auto';
            menu.style.bottom = 'auto';
            menu.offsetHeight;
            var rect = menu.getBoundingClientRect();

            // Flip horizontally if it overflows viewport right edge
            if (rect.right > vw - 4) {
                menu.style.left = 'auto';
                menu.style.right = (vw - badgeRect.right) + 'px';
            }

            // Flip vertically if it overflows viewport bottom edge
            if (rect.bottom > vh - 4) {
                menu.style.top = 'auto';
                menu.style.bottom = (vh - badgeRect.top + 2) + 'px';
            }
        } else {
            // Restore default positioning
            menu.style.position = '';
            menu.style.top = '';
            menu.style.bottom = '';
            menu.style.left = '';
            menu.style.right = '';
        }
    }
}

function setStatus(jobId, status, btn) {
    var menu = btn.closest('.status-menu');
    if (menu) menu.style.display = 'none';

    fetch('/job/' + jobId + '/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: status }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.ok) {
            // Build URL preserving all current filter/pagination state
            var params = [];
            var searchEl = document.getElementById('search-input');
            if (searchEl && searchEl.value) params.push('search=' + encodeURIComponent(searchEl.value));
            var sinceEl = document.querySelector('[name="since"]');
            if (sinceEl && sinceEl.value) params.push('since=' + encodeURIComponent(sinceEl.value));
            var filterEl = document.getElementById('filter-state');
            if (filterEl && filterEl.value) params.push('filters=' + encodeURIComponent(filterEl.value));
            var perPageEl = document.getElementById('per-page-select');
            if (perPageEl) params.push('per_page=' + encodeURIComponent(perPageEl.value));
            if (document.querySelector('.col-check')) params.push('select=1');
            var pageInfo = document.querySelector('.pagination-info');
            if (pageInfo) {
                var match = pageInfo.textContent.match(/Page\s+(\d+)\s+of/);
                if (match) params.push('page=' + match[1]);
            }
            var url = '/table' + (params.length ? '?' + params.join('&') : '');
            htmx.ajax('GET', url, {target: '#table-container', swap: 'innerHTML'});
        }
    })
    .catch(function(err) {
        console.error('[Status] Error updating status:', err);
    });
}

// -- Bulk Status: header-level dropdown when SELECT active & checkboxes checked --
// REMOVED: SELECT button and bulk status removed per user request.
// Status changes are applied per-row via the status-badge dropdown menu.

// Close status menus when clicking outside
document.body.addEventListener('click', function(e) {
    if (!e.target.closest('.status-badge') && !e.target.closest('.status-menu')) {
        document.querySelectorAll('.status-menu').forEach(function(m) {
            m.style.display = 'none';
        });
    }
});

// -- Sort State: populate #sort-state from localStorage on STATUS tab load -------

/**
 * Convert localStorage fb-sort-config (JSON array) to compact col:dir,col:dir format.
 * Returns empty string if no config.
 */
function getSortParam() {
    var config = getSortConfig();
    if (config.length === 0) return '';
    var parts = [];
    for (var i = 0; i < config.length; i++) {
        parts.push(config[i].col + ':' + config[i].dir);
    }
    return parts.join(',');
}

// Populate #sort-state when STATUS tab is loaded
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target && evt.detail.target.id === 'main-content') {
        var sortState = document.getElementById('sort-state');
        if (sortState) {
            sortState.value = getSortParam();
        }
    }
});

// -- Header-click handler: toggle sort direction and reload table with page=1 -----

document.body.addEventListener('click', function(e) {
    var th = e.target.closest('.th-sortable');
    if (!th) return;

    var col = th.getAttribute('data-col');
    if (!col) return;

    var sortState = document.getElementById('sort-state');
    if (!sortState) return;

    var currentSort = sortState.value || '';
    var parts = currentSort ? currentSort.split(',') : [];
    var found = false;
    var newParts = [];

    for (var i = 0; i < parts.length; i++) {
        var pair = parts[i].split(':');
        if (pair[0] === col) {
            found = true;
            // Toggle direction
            var newDir = pair[1] === 'asc' ? 'desc' : 'asc';
            newParts.push(col + ':' + newDir);
        } else {
            newParts.push(parts[i]);
        }
    }

    if (!found) {
        // Column not sorted yet — add it as the primary sort (asc)
        newParts.unshift(col + ':asc');
    }

    var newSort = newParts.join(',');
    sortState.value = newSort;

    // Reload table with new sort, resetting page to 1
    var params = 'sort=' + encodeURIComponent(newSort) + '&page=1';
    var search = document.getElementById('search-input');
    if (search && search.value) params += '&search=' + encodeURIComponent(search.value);
    var since = document.querySelector('[name="since"]');
    if (since) params += '&since=' + encodeURIComponent(since.value);
    var filterState = document.getElementById('filter-state');
    if (filterState && filterState.value) params += '&filters=' + encodeURIComponent(filterState.value);

    htmx.ajax('GET', '/table?' + params, {
        target: '#table-container',
        swap: 'innerHTML'
    });
});

// -- Re-populate #sort-state after any table swap (keeps indicator rendering in sync) --

document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target && evt.detail.target.id === 'table-container') {
        var sortState = document.getElementById('sort-state');
        if (sortState) {
            // If the table HTML contains a sort value (from template context), sync it
            var tableHtml = evt.detail.target.innerHTML;
            var sortMatch = tableHtml.match(/sort[=:]([a-z_]+:[a-z]+(?:,[a-z_]+:[a-z]+)*)/);
            if (sortMatch) {
                // The sort value is already in the sort-state; keep it in sync
            }
        }
    }
});