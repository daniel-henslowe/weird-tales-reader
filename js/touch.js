/* === iPad Touch Gestures === */
(function () {
  'use strict';

  if (!window.ReaderNav) return;

  const SWIPE_THRESHOLD = 50;   // minimum px for a swipe
  const TAP_ZONE = 0.20;        // 20% from each edge

  let touchStartX = 0;
  let touchStartY = 0;
  let touchStartTime = 0;

  document.addEventListener('touchstart', (e) => {
    if (e.touches.length !== 1) return;
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    touchStartTime = Date.now();
  }, { passive: true });

  document.addEventListener('touchend', (e) => {
    if (e.changedTouches.length !== 1) return;

    const endX = e.changedTouches[0].clientX;
    const endY = e.changedTouches[0].clientY;
    const deltaX = endX - touchStartX;
    const deltaY = endY - touchStartY;
    const elapsed = Date.now() - touchStartTime;

    // Ignore if interacting with controls
    const target = e.target;
    if (target.closest('.toc-drawer, .settings-panel, .site-nav, .reader-nav, .section-nav, .issue-nav, a, button, input')) {
      return;
    }

    // Swipe detection (horizontal swipe, quick gesture)
    if (Math.abs(deltaX) > SWIPE_THRESHOLD && Math.abs(deltaX) > Math.abs(deltaY) * 1.5 && elapsed < 500) {
      if (deltaX < 0) {
        // Swipe left = next
        ReaderNav.nextSection();
      } else {
        // Swipe right = previous
        ReaderNav.prevSection();
      }
      return;
    }

    // Tap zone detection (quick tap, minimal movement)
    if (elapsed < 300 && Math.abs(deltaX) < 10 && Math.abs(deltaY) < 10) {
      const screenWidth = window.innerWidth;
      const tapX = endX;

      if (tapX < screenWidth * TAP_ZONE) {
        // Left zone tap = previous section
        ReaderNav.prevSection();
      } else if (tapX > screenWidth * (1 - TAP_ZONE)) {
        // Right zone tap = next section
        ReaderNav.nextSection();
      }
      // Center tap = do nothing (allow normal interaction)
    }
  }, { passive: true });
})();
