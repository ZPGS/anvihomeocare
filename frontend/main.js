// Simple reveal on scroll
const sections = document.querySelectorAll(".slide-up");

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = 1;
      }
    });
  },
  { threshold: 0.2 },
);

sections.forEach((s) => observer.observe(s));
