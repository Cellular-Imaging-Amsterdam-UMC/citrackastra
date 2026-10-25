document.addEventListener('DOMContentLoaded', async () => {
  if (!document.querySelector('[data-sample]')) return;
  const response = await fetch('assets/examples.json');
  const { samples } = await response.json();
  const ns = 'http://www.w3.org/2000/svg';
  for (const viewer of document.querySelectorAll('[data-sample]')) {
    const index = Number(viewer.dataset.sample);
    const sample = samples[index];
    const slider = document.querySelector(`[data-frame="${index}"]`);
    const button = document.querySelector(`[data-play="${index}"]`);
    const output = document.getElementById(`frame-${index}`);
    const svg = viewer.querySelector('svg');
    let timer = null;
    const render = () => {
      const frame = Number(slider.value);
      output.value = String(frame);
      viewer.querySelector('img').src = sample.images[frame];
      svg.replaceChildren();
      for (const [track, values] of Object.entries(sample.tracks)) {
        const color = `hsl(${(Number(track) * 137.508) % 360} 85% 70%)`;
        const visible = values.filter(p => p[0] <= frame);
        if (visible.length > 1) {
          const path = document.createElementNS(ns, 'polyline');
          path.setAttribute('points', visible.map(p => `${p[1] * 1000},${p[2] * 1000}`).join(' '));
          path.setAttribute('fill', 'none'); path.setAttribute('stroke', color); path.setAttribute('stroke-width', '3');
          svg.append(path);
        }
        const current = visible.find(p => p[0] === frame);
        if (current) {
          const circle = document.createElementNS(ns, 'circle');
          circle.setAttribute('cx', String(current[1] * 1000)); circle.setAttribute('cy', String(current[2] * 1000));
          circle.setAttribute('r', '5'); circle.setAttribute('fill', color); circle.setAttribute('stroke', '#111'); circle.setAttribute('stroke-width', '1');
          svg.append(circle);
        }
      }
    };
    slider.addEventListener('input', render);
    button.addEventListener('click', () => {
      if (timer) { clearInterval(timer); timer = null; button.textContent = 'Play'; return; }
      button.textContent = 'Pause';
      timer = setInterval(() => { slider.value = String((Number(slider.value) + 1) % sample.images.length); render(); }, 700);
    });
    render();
  }
});
