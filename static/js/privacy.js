try{
  const toggle = document.getElementById('menuToggle');
  const panel = document.getElementById('mobilePanel');
  toggle.addEventListener('click', () => {
    const open = panel.classList.toggle('open');
    toggle.setAttribute('aria-expanded', open);
  });
}catch(e){}

try{
  const links = Array.from(document.querySelectorAll('#tocList a'));
  const sections = links.map(a => document.querySelector(a.getAttribute('href')));
  const setActive = () => {
    let idx = 0;
    const pos = window.scrollY + 110;
    sections.forEach((s, i) => { if(s && s.offsetTop <= pos) idx = i; });
    links.forEach((a,i) => a.classList.toggle('active', i === idx));
  };
  window.addEventListener('scroll', setActive, {passive:true});
  setActive();
}catch(e){}