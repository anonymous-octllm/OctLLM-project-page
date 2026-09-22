(() => {
  'use strict';
  const assets = window.MODEL_ASSETS || [];
  const release = window.OCTLLM_RELEASE || {};
  const viewer = document.getElementById('asset-viewer');
  const stage = document.getElementById('model-stage');
  const picker = document.getElementById('model-picker');
  const tabs = [...document.querySelectorAll('[data-gallery]')];
  const status = document.getElementById('model-status');
  const retry = document.getElementById('retry-model');
  const progress = document.getElementById('model-progress-fill');
  const remembered = new Map();
  const modelSources = new Map();
  let currentAsset, currentModelSrc, activeGallery = 'image', viewerModule, loadTimer, moduleRetries = 0, modelRetries = 0;

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const makeImage = (src, alt, className) => {
    const img = make('img', className);
    img.src = src;
    img.alt = alt;
    img.loading = 'lazy';
    img.decoding = 'async';
    return img;
  };

  function modelError() {
    clearTimeout(loadTimer);
    viewer.showPoster?.();
    status.textContent = '3D preview unavailable. Try again or download the GLB.';
    retry.hidden = false;
    stage.setAttribute('aria-busy', 'false');
    progress.style.width = '0%';
  }
  function waitForModel() {
    clearTimeout(loadTimer);
    status.textContent = 'Loading 3D model…';
    retry.hidden = true;
    stage.setAttribute('aria-busy', 'true');
    progress.style.width = '0%';
    // A failed module/WebGL connection should not leave an indefinite spinner.
    loadTimer = setTimeout(modelError, 45000);
  }
  async function loadViewer() {
    if (!viewerModule) {
      waitForModel();
      const moduleUrl = new URL('./assets/vendor/model-viewer-4.2.0.min.js', document.baseURI);
      if (moduleRetries) moduleUrl.searchParams.set('retry', String(moduleRetries));
      viewerModule = import(moduleUrl.href).catch(error => {
        // Browsers cache failed module fetches; a retry needs a fresh module URL.
        moduleRetries += 1;
        viewerModule = undefined;
        throw error;
      });
    }
    try { await viewerModule; return true; }
    catch { modelError(); return false; }
  }
  function resetCamera() {
    viewer.setAttribute('camera-orbit', currentAsset?.cameraOrbit || '30deg 75deg 105%');
    viewer.setAttribute('camera-target', 'auto auto auto');
    viewer.setAttribute('field-of-view', '30deg');
    viewer.resetTurntableRotation?.();
    viewer.jumpCameraToGoal?.();
  }
  function selectAsset(asset, { reload = false } = {}) {
    if (!asset) return;
    const source = reload ? `${asset.src}?retry=${++modelRetries}` : (modelSources.get(asset.id) || asset.src);
    if (currentAsset?.id === asset.id && viewer.getAttribute('src') === source) {
      [...picker.children].forEach(button => button.setAttribute('aria-pressed', String(button.dataset.asset === asset.id)));
      return;
    }
    currentAsset = asset;
    currentModelSrc = source;
    modelSources.set(asset.id, source);
    remembered.set(activeGallery, asset.id);
    document.getElementById('model-name').textContent = asset.name;
    const condition = document.getElementById('model-condition');
    condition.replaceChildren();
    if (asset.input) {
      condition.append(make('p', 'condition-label', 'Input image'), makeImage(asset.input, `Conditioning image for ${asset.name}`, 'condition-image'));
    } else if (asset.prompt) {
      const details = make('details');
      details.append(make('summary', '', 'View text prompt'), make('blockquote', '', asset.prompt));
      condition.append(details);
    }
    const download = document.getElementById('download-model');
    download.href = asset.src;
    download.download = `${asset.id}.glb`;
    download.setAttribute('aria-label', `Download ${asset.name} GLB`);
    document.getElementById('model-poster').src = asset.poster;
    document.getElementById('model-poster').alt = `Preview of ${asset.name}`;
    viewer.setAttribute('alt', `${asset.name}, generated 3D mesh. Drag or use arrow keys to rotate; scroll or pinch to zoom.`);
    viewer.setAttribute('aria-label', `${asset.name}, interactive generated 3D model`);
    // Keep the poster visible until this particular model has finished loading.
    viewer.showPoster?.();
    waitForModel();
    viewer.setAttribute('src', source);
    resetCamera();
    [...picker.children].forEach(button => button.setAttribute('aria-pressed', String(button.dataset.asset === asset.id)));
  }
  viewer.addEventListener('load', event => {
    if (!currentModelSrc || new URL(event.detail.url, location.href).href !== new URL(currentModelSrc, location.href).href) return;
    clearTimeout(loadTimer);
    retry.hidden = true;
    status.textContent = '3D model ready.';
    stage.setAttribute('aria-busy', 'false');
    progress.style.width = '0%';
    viewer.dismissPoster();
    resetCamera();
  });
  viewer.addEventListener('error', modelError);
  viewer.addEventListener('progress', event => {
    progress.style.width = event.detail.totalProgress >= 1 ? '0%' : `${event.detail.totalProgress * 100}%`;
  });
  retry.addEventListener('click', async () => {
    const asset = currentAsset;
    viewer.removeAttribute('src');
    const ready = await loadViewer();
    // The viewer also caches failed GLB promises. Retain each fresh URL for later selections.
    if (ready && asset === currentAsset) selectAsset(asset, { reload: true });
  });
  document.getElementById('reset-view').addEventListener('click', resetCamera);

  function renderGallery(mode) {
    activeGallery = mode;
    tabs.forEach(tab => {
      const selected = tab.dataset.gallery === mode;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    document.getElementById('gallery-panel').setAttribute('aria-labelledby', `${mode}-tab`);
    picker.replaceChildren();
    const choices = assets.filter(asset => asset.conditionType === mode);
    choices.forEach(asset => {
      const button = make('button', 'model-option');
      button.type = 'button';
      button.dataset.asset = asset.id;
      button.setAttribute('aria-label', `Explore ${asset.name} in 3D`);
      button.append(makeImage(asset.poster, ''), make('span', 'model-option-name', asset.name));
      button.addEventListener('click', () => { selectAsset(asset); loadViewer(); });
      picker.append(button);
    });
    selectAsset(choices.find(asset => asset.id === remembered.get(mode)) || choices[0]);
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => { renderGallery(tab.dataset.gallery); loadViewer(); });
    tab.addEventListener('keydown', event => {
      if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (i + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      tabs[index].focus();
      renderGallery(tabs[index].dataset.gallery);
      loadViewer();
    });
  });
  renderGallery('image');
  clearTimeout(loadTimer); // Begin loading only when the gallery approaches the viewport.
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); loadViewer(); }
    }, { rootMargin: '500px' });
    observer.observe(stage);
  } else { loadViewer(); }

  const expand = document.getElementById('fullscreen-model');
  const isolated = new Map();
  function setExpandedFallback(expanded) {
    stage.classList.toggle('is-expanded', expanded);
    if (expanded) {
      // Isolate siblings along the whole ancestor chain, keeping the viewer live.
      for (let node = stage; node.parentElement && node !== document.body; node = node.parentElement) {
        [...node.parentElement.children].filter(sibling => sibling !== node).forEach(sibling => {
          isolated.set(sibling, sibling.inert);
          sibling.inert = true;
        });
      }
      stage.setAttribute('role', 'dialog');
      stage.setAttribute('aria-modal', 'true');
      stage.setAttribute('aria-label', 'Expanded 3D viewer');
    } else {
      isolated.forEach((wasInert, node) => { node.inert = wasInert; });
      isolated.clear();
      stage.removeAttribute('role');
      stage.removeAttribute('aria-modal');
      stage.removeAttribute('aria-label');
      expand.focus();
    }
  }
  function syncFullscreen() {
    const expanded = document.fullscreenElement === stage || stage.classList.contains('is-expanded');
    expand.setAttribute('aria-label', expanded ? 'Exit expanded 3D viewer' : 'Expand 3D viewer');
    expand.title = expanded ? 'Exit expanded 3D viewer' : 'Expand 3D viewer';
    expand.textContent = expanded ? '×' : '⛶';
    document.body.classList.toggle('viewer-expanded', stage.classList.contains('is-expanded'));
  }
  expand.addEventListener('click', async () => {
    if (document.fullscreenElement === stage) await document.exitFullscreen();
    else if (stage.classList.contains('is-expanded')) setExpandedFallback(false);
    else {
      try {
        if (!stage.requestFullscreen) throw new Error('Fullscreen API unavailable');
        await stage.requestFullscreen();
      } catch { setExpandedFallback(true); }
    }
    syncFullscreen();
  });
  document.addEventListener('fullscreenchange', syncFullscreen);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && stage.classList.contains('is-expanded')) {
      setExpandedFallback(false);
      syncFullscreen();
      expand.focus();
    }
  });
  stage.addEventListener('keydown', event => {
    if (event.key !== 'Tab' || !stage.classList.contains('is-expanded')) return;
    if (event.shiftKey && document.activeElement === viewer) {
      event.preventDefault();
      expand.focus();
    } else if (!event.shiftKey && document.activeElement === expand) {
      event.preventDefault();
      // The pinned viewer does not delegate focus from its host to its canvas.
      const input = viewer.shadowRoot?.querySelector('.userInput');
      (input || document.getElementById('reset-view')).focus();
    }
  });

  const examples = document.getElementById('understanding-examples');
  (window.OCTLLM_GALLERY?.understanding || []).forEach(example => {
    const article = make('article', 'understanding-card');
    const object = make('div', 'understanding-object');
    example.images.forEach((src, i) => object.append(makeImage(src, `${example.name}, input 3D object, viewpoint ${i + 1}`)));
    const content = make('div', 'understanding-text');
    content.append(make('h3', '', example.name), make('blockquote', '', `“${example.description}”`));
    article.append(object, content);
    examples.append(article);
  });

  const figureDialog = document.getElementById('figure-dialog');
  figureDialog.querySelector('.dialog-close').addEventListener('click', () => figureDialog.close());
  figureDialog.addEventListener('close', () => document.body.classList.remove('modal-open'));
  figureDialog.addEventListener('click', event => {
    if (event.target !== figureDialog) return;
    const box = figureDialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) figureDialog.close();
  });
  document.querySelectorAll('[data-figure]').forEach(button => button.addEventListener('click', () => {
    document.getElementById('figure-dialog-title').textContent = button.dataset.title;
    const img = document.getElementById('figure-dialog-image');
    img.src = button.dataset.figure;
    img.alt = button.querySelector('img').alt;
    figureDialog.showModal();
    document.body.classList.add('modal-open');
  }));

  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const videos = [...document.querySelectorAll('video')];
  const playback = new Map(videos.map(video => [video, { visible: false, userPaused: false, suspended: false }]));
  function filmAllowsPlayback(video) {
    const page = video.closest('.film-page');
    return !page || page.classList.contains('is-active');
  }
  function loadVideo(video) {
    const sources = [...video.querySelectorAll('source[data-src]')];
    if (!sources.length) return;
    sources.forEach(source => { source.src = source.dataset.src; delete source.dataset.src; });
    video.load();
  }
  function syncVideoControl(video) {
    const button = document.querySelector(`[data-video="${video.id}"]`);
    if (!button) return;
    button.querySelector('.toggle-icon').textContent = video.paused ? '▶' : 'Ⅱ';
    button.querySelector('.toggle-label').textContent = video.paused ? 'Play' : 'Pause';
    button.setAttribute('aria-label', `${video.paused ? 'Play' : 'Pause'} overview animation`);
  }
  function playVideo(video) {
    loadVideo(video);
    video.play().catch(() => syncVideoControl(video));
  }
  function suspend(video) {
    if (video.paused) return;
    playback.get(video).suspended = true;
    video.pause();
  }
  videos.forEach(video => {
    const state = playback.get(video);
    video.muted = true;
    video.addEventListener('play', () => { state.userPaused = false; syncVideoControl(video); });
    video.addEventListener('pause', () => {
      if (!state.suspended) state.userPaused = true;
      state.suspended = false;
      syncVideoControl(video);
    });
    document.querySelector(`[data-video="${video.id}"]`)?.addEventListener('click', () => {
      if (video.paused) playVideo(video);
      else { state.userPaused = true; video.pause(); }
    });
    syncVideoControl(video);
  });
  if ('IntersectionObserver' in window) {
    const preloadObserver = new IntersectionObserver(entries => entries.forEach(({ target, isIntersecting }) => {
      if (isIntersecting && filmAllowsPlayback(target)) { loadVideo(target); preloadObserver.unobserve(target); }
    }), { rootMargin: '300px' });
    const videoObserver = new IntersectionObserver(entries => entries.forEach(({ target: video, isIntersecting }) => {
      const state = playback.get(video);
      state.visible = isIntersecting;
      if (!isIntersecting || !filmAllowsPlayback(video)) suspend(video);
      else if (!reducedMotion.matches && !state.userPaused && !document.hidden) playVideo(video);
    }), { threshold: 0.3 });
    videos.forEach(video => {
      preloadObserver.observe(video);
      if (!video.closest('.film-page')) videoObserver.observe(video);
    });
  } else { videos.forEach(loadVideo); }
  document.addEventListener('visibilitychange', () => videos.forEach(video => {
    const state = playback.get(video);
    if (document.hidden) suspend(video);
    else if (state.visible && filmAllowsPlayback(video) && !state.userPaused && !reducedMotion.matches) playVideo(video);
  }));
  reducedMotion.addEventListener('change', () => { if (reducedMotion.matches) videos.forEach(suspend); });

  const pager = document.querySelector('.film-pager');
  const filmTabs = [...document.querySelectorAll('[data-film]')];
  const filmPages = [...pager.querySelectorAll('.film-page')];
  const filmCaption = document.getElementById('film-caption');
  let filmIndex = Number(pager.dataset.index) || 0;
  let pagerVisible = false;
  function syncFilmPlayback() {
    filmPages.forEach((page, i) => {
      const video = page.querySelector('video');
      const state = playback.get(video);
      const active = i === filmIndex;
      state.visible = pagerVisible && active;
      if (!state.visible) suspend(video);
      else if (!state.userPaused && !reducedMotion.matches && !document.hidden) playVideo(video);
    });
  }
  function setFilm(index) {
    const count = filmPages.length;
    filmIndex = ((index % count) + count) % count;
    pager.dataset.index = String(filmIndex);
    filmPages.forEach((page, i) => {
      page.classList.toggle('is-active', i === filmIndex);
      page.inert = i !== filmIndex;
    });
    filmTabs.forEach(tab => {
      const selected = Number(tab.dataset.film) === filmIndex;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    filmCaption.textContent = filmPages[filmIndex].dataset.caption;
    const turns = [...pager.querySelectorAll('.film-turn')];
    const focusedTurn = turns.find(button => document.activeElement === button);
    turns.forEach(button => {
      const dir = Number(button.dataset.dir);
      button.inert = dir < 0 ? filmIndex === 0 : filmIndex === filmPages.length - 1;
    });
    if (focusedTurn?.inert) (turns.find(button => !button.inert) || filmTabs[filmIndex]).focus();
    syncFilmPlayback();
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      pagerVisible = entries.some(entry => entry.isIntersecting);
      syncFilmPlayback();
    }, { threshold: 0.3 }).observe(pager);
  } else { pagerVisible = true; }
  filmTabs.forEach((tab, i) => {
    tab.addEventListener('click', () => setFilm(Number(tab.dataset.film)));
    tab.addEventListener('keydown', event => {
      if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? filmTabs.length - 1 : (i + (event.key === 'ArrowRight' ? 1 : -1) + filmTabs.length) % filmTabs.length;
      filmTabs[next].focus();
      setFilm(Number(filmTabs[next].dataset.film));
    });
  });
  pager.querySelectorAll('.film-turn').forEach(button => {
    button.addEventListener('click', () => setFilm(filmIndex + Number(button.dataset.dir)));
  });
  const viewport = pager.querySelector('.film-viewport');
  let swipe = null;
  viewport.addEventListener('pointerdown', event => {
    if (event.button) return;
    const bounds = viewport.getBoundingClientRect();
    if (event.clientY > bounds.top + bounds.height * 0.82) return;
    swipe = { id: event.pointerId, x: event.clientX };
  });
  viewport.addEventListener('pointerup', event => {
    if (!swipe || swipe.id !== event.pointerId) return;
    const dx = event.clientX - swipe.x;
    swipe = null;
    if (Math.abs(dx) > 60) setFilm(filmIndex + (dx < 0 ? 1 : -1));
  });
  viewport.addEventListener('pointercancel', () => { swipe = null; });

  // Empty release fields stay out of the interface until real resources exist.
  ['paper', 'code', 'model'].forEach(key => {
    if (typeof release[key] !== 'string' || !release[key].trim()) return;
    try {
      const url = new URL(release[key], location.href);
      if (!['http:', 'https:'].includes(url.protocol)) return;
      const link = document.querySelector(`[data-resource="${key}"]`);
      link.href = url.href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.hidden = false;
    } catch { /* Ignore invalid release links. */ }
  });
  if (typeof release.citation === 'string' && release.citation.trim()) {
    document.getElementById('citation').hidden = false;
    document.getElementById('bibtex').textContent = release.citation.trim();
    document.getElementById('copy-citation').addEventListener('click', async () => {
      const status = document.getElementById('copy-status');
      try { await navigator.clipboard.writeText(release.citation.trim()); status.textContent = 'Citation copied.'; }
      catch { status.textContent = 'Select the citation above to copy it.'; }
    });
  }
})();
