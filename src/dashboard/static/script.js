// Cyberpunk Dashboard — JS for SSE progress, debug, clean-db, select-all, auto-apply
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
        var isLight = document.documentElement.getAttribute('data-theme') === 'light';
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

        // Update score (only while running and not ducking/jumping)
        if (this.running && !this.isDucking && !this.isJumping) {
            this.score += Math.ceil(speed * 0.1);
            if (this.score > this.hiScore) {
                this.hiScore = this.score;
                localStorage.setItem('dino-hi-score', this.hiScore);
            }
        }

        // Move obstacles and clouds
        var speed = 4 + (this.targetPct / 100) * 3;
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
        var wrap = document.getElementById('progress-container');
        if (!wrap) return;

        if (data.error) {
            wrap.innerHTML = '<div class="scan-progress scan-progress-error"><div class="progress-track"><div class="progress-fill" style="width:100%"></div></div></div>';
        } else {
            wrap.innerHTML = '<div class="scan-progress scan-progress-done"><div class="progress-track"><div class="progress-fill" style="width:100%"></div></div></div>';
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

        // Show STOP button in header if debug mode is on
        var debugCheckbox = document.getElementById('debug-mode');
        var stopBtn = document.getElementById('stop-btn');
        if (stopBtn && debugCheckbox && debugCheckbox.checked) {
            stopBtn.style.display = 'inline-block';
        }

        // Expand the dino banner and init dino renderer
        var progressContainer = document.getElementById('progress-container');
        var dinoBanner = document.getElementById('dino-banner');
        if (dinoBanner) {
            // rAF to force a frame separation — otherwise CSS transition
            // won't fire because the element was just inserted by HTMX.
            // Also ensures the canvas renderer sees the expanded dimensions.
            requestAnimationFrame(function () {
                dinoBanner.classList.add('expanded');

                // Create canvas renderer AFTER expansion so resize() sees 45px
                var canvas = document.getElementById('dino-canvas');
                if (canvas) {
                    dinoRenderer = new DinoCanvasRenderer(canvas, dinoBanner);
                    dinoRenderer.start();
                }
            });
        }

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

    // -- Debug Checkbox + HEADER buttons (CLEAN DB + STOP) ----------------

    var debugCheckbox = document.getElementById('debug-mode');
    if (debugCheckbox) {
        debugCheckbox.addEventListener('change', function () {
            var isChecked = this.checked;
            // Toggle CLEAN DB
            var cleanBtn = document.getElementById('clean-db-btn');
            if (cleanBtn) {
                cleanBtn.style.display = isChecked ? 'inline-block' : 'none';
            }
            // Toggle STOP button (only if scan is running)
            var stopBtn = document.getElementById('stop-btn');
            if (stopBtn) {
                var scanBtn = document.getElementById('scan-btn');
                var isScanRunning = scanBtn && scanBtn.disabled;
                stopBtn.style.display = (isChecked && isScanRunning) ? 'inline-block' : 'none';
            }
            console.log('[Debug] Debug mode ' + (isChecked ? 'ON' : 'OFF') + ' — limiting to 3 results per scraper.');
        });
    }

// After clean-db, hide CLEAN DB and STOP buttons
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/clean-db') {
            // Stop scan if running (server stops it)
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            enableScanButton();
            var progressContainer = document.getElementById('progress-container');
            if (progressContainer) {
                progressContainer.classList.remove('expanded');
            }
            dinoRenderer = null;

            // Hide STOP and CLEAN DB buttons in header
            var stopBtn = document.getElementById('stop-btn');
            if (stopBtn) stopBtn.style.display = 'none';
            var cleanBtn = document.getElementById('clean-db-btn');
            if (cleanBtn) cleanBtn.style.display = 'none';

            var tableContainer = document.getElementById('table-container');
            if (tableContainer) {
                htmx.ajax('GET', '/table', {target: '#table-container', swap: 'innerHTML'});
            }
        }
    });

    // After /scan/stop, close SSE, re-enable SCAN, collapse progress, kill dino
    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/scan/stop') {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            enableScanButton();
            var progressContainer = document.getElementById('progress-container');
            if (progressContainer) {
                progressContainer.classList.remove('expanded');
            }
            dinoRenderer = null;

            // Hide STOP button in header
            var stopBtn = document.getElementById('stop-btn');
            if (stopBtn) stopBtn.style.display = 'none';
        }
    });

    // -- Select-All Checkbox ----------------------------------------------

    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.id === 'select-all') {
            var checkboxes = document.querySelectorAll('.job-select');
            for (var i = 0; i < checkboxes.length; i++) {
                checkboxes[i].checked = e.target.checked;
            }
        }
    });

    // -- Auto-Apply handler --------------------------------------------------

    document.body.addEventListener('click', function (e) {
        var target = e.target;
        if (target && target.id === 'auto-apply-btn') {
            e.preventDefault();
            var selected = document.querySelectorAll('.job-select:checked');
            var ids = [];
            for (var i = 0; i < selected.length; i++) {
                ids.push(parseInt(selected[i].value, 10));
            }
            if (ids.length === 0) return;

            var btn = document.getElementById('auto-apply-btn');
            btn.disabled = true;
            btn.textContent = 'APPLYING...';

            fetch('/apply/auto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_ids: ids }),
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                console.log('[Auto-Apply] Results:', data.results);
                // Refresh the table to show updated statuses
                htmx.ajax('GET', '/table', {target: '#table-container', swap: 'innerHTML'});
            })
            .catch(function (err) {
                console.error('[Auto-Apply] Error:', err);
            })
            .finally(function () {
                btn.disabled = false;
                btn.textContent = 'AUTO-APPLY';
                // Uncheck all selected checkboxes
                var checkboxes = document.querySelectorAll('.job-select:checked');
                for (var i = 0; i < checkboxes.length; i++) {
                    checkboxes[i].checked = false;
                }
                // Re-enable check logic
                var selectAll = document.getElementById('select-all');
                if (selectAll) selectAll.checked = false;
                var checked = document.querySelectorAll('.job-select:checked');
                if (checked.length === 0) {
                    btn.disabled = true;
                    btn.style.opacity = '0.4';
                    btn.style.cursor = 'not-allowed';
                    btn.title = 'Auto-Apply (next session)';
                }
            });
        }
    });

    // -- Enable Auto-Apply when selections exist --------------------------

    document.body.addEventListener('change', function (e) {
        if (e.target && e.target.classList.contains('job-select')) {
            var btn = document.getElementById('auto-apply-btn');
            if (!btn) return;
            var checked = document.querySelectorAll('.job-select:checked');
            if (checked.length > 0) {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
                btn.title = 'Auto-Apply to ' + checked.length + ' selected job(s)';
            } else {
                btn.disabled = true;
                btn.style.opacity = '0.4';
                btn.style.cursor = 'not-allowed';
                btn.title = 'Auto-Apply (next session)';
            }
        }
    });

    // -- Theme Toggle -----------------------------------------------------

    var themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        // Load saved preference
        var saved = localStorage.getItem('dashboard-theme');
        if (saved === 'light') themeToggle.checked = true;

        themeToggle.addEventListener('change', function () {
            var theme = this.checked ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('dashboard-theme', theme);
        });
    }

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
                var tc = document.getElementById('table-container');
                if (tc) htmx.trigger(tc, 'load');
            }
        });
    }

    // -- HTMX Event Handlers for Datos Panel -----------------------------

    // Before SAVE: disable button to prevent double-click
    document.body.addEventListener('htmx:beforeRequest', function (evt) {
        if (evt.detail.pathInfo.requestPath === '/datos/fields/save') {
            var btn = document.querySelector('.btn-save');
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
            var btn = document.querySelector('.btn-save');
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

    // -- SELECT Button Toggle --------------------------------------------

    var selectBtn = document.querySelector('.btn-toggle');
    if (selectBtn) {
        selectBtn.addEventListener('click', function () {
            var isEnabled = this.getAttribute('hx-get') === '/select/toggle?enabled=true';
            this.setAttribute('hx-get', isEnabled ? '/select/toggle?enabled=false' : '/select/toggle?enabled=true');
            this.textContent = isEnabled ? 'SELECT' : 'SELECT';
        });
    }

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

    // -- SELECT Button Toggle --------------------------------------------

    var selectBtn = document.querySelector('.btn-toggle');
    if (selectBtn) {
        selectBtn.addEventListener('click', function () {
            var isEnabled = this.classList.toggle('btn-toggle-active');
            htmx.ajax('GET', '/select/toggle?enabled=' + isEnabled, {
                target: '#table-container',
                swap: 'innerHTML'
            });
        });
    }

})();

// -- Filter Dropdown -------------------------------------------------------

(function () {
    'use strict';

    var filterBtn = document.getElementById('filter-btn');
    var filterMenu = document.getElementById('filter-menu');

    if (filterBtn && filterMenu) {
        // Toggle dropdown on button click
        filterBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            var isVisible = filterMenu.style.display !== 'none';
            filterMenu.style.display = isVisible ? 'none' : 'block';
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function (e) {
            var wrapper = document.getElementById('filter-wrapper');
            if (wrapper && !wrapper.contains(e.target)) {
                filterMenu.style.display = 'none';
            }
        });

        // Refresh table when any filter checkbox changes
        filterMenu.addEventListener('change', function () {
            var checkboxes = document.querySelectorAll('.filter-checkbox:checked');
            var activeKeys = [];
            for (var i = 0; i < checkboxes.length; i++) {
                activeKeys.push(checkboxes[i].getAttribute('data-filter-key'));
            }
            var filtersParam = activeKeys.join(',');
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
        });
    }
})();