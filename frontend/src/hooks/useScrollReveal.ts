import { useEffect } from 'react';

/**
 * Triggers scroll-reveal animations on elements with the `reveal` class.
 * Uses IntersectionObserver to add the `visible` class when elements enter the viewport.
 */
export function useScrollReveal() {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
          }
        });
      },
      { threshold: 0.12 }
    );

    // Observe all elements with the `reveal` class
    const elements = document.querySelectorAll('.reveal');
    elements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);
}
