document.addEventListener("DOMContentLoaded", () => {
  // particles
  if (window.tsParticles) {
    tsParticles.load("particles", {
      background: { color: { value: "transparent" } },
      fpsLimit: 60,
      interactivity: {
        events: { onHover: { enable: true, mode: "repulse" } },
        modes: { repulse: { distance: 110 } }
      },
      particles: {
        color: { value: ["#2A6FF2", "#67B7FF", "#8CF0D6", "#FFD6A6", "#FFB3C7"] },
        links: { enable: true, color: "#67B7FF", distance: 135, opacity: 0.25, width: 1 },
        move: { enable: true, speed: 1.1, outModes: { default: "out" } },
        number: { value: 40, density: { enable: true, area: 900 } },
        opacity: { value: 0.55 },
        shape: { type: "circle" },
        size: { value: { min: 1, max: 4 } }
      },
      detectRetina: true
    });
  }
});