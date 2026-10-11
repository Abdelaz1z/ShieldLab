/*
  Bridge between Room Designer (bundled into index.html by build.py) and Streamlit.

  Speaks the Streamlit component protocol by hand (no npm package needed): announces itself,
  takes the frame height from the page, and sends the current plan back to Python when the user
  presses "Send to survey". The background photo is left out of what is sent: it can be several
  megabytes and the survey does not use it.
*/
(function () {
  function post(type, extra) {
    var message = Object.assign({ isStreamlitMessage: true, type: type }, extra || {});
    window.parent.postMessage(message, '*');
  }

  var height = 760;
  window.addEventListener('message', function (event) {
    var data = event.data || {};
    if (data.type !== 'streamlit:render') return;
    var wanted = data.args && data.args.height;
    if (wanted && wanted !== height) height = wanted;
    post('streamlit:setFrameHeight', { height: height });
  });

  function planToSend() {
    var plan = JSON.parse(JSON.stringify(Editor.getDesign()));
    plan.background = null;
    return plan;
  }

  function addButton() {
    var button = document.createElement('button');
    button.type = 'button';
    button.id = 'shieldlabSend';
    button.textContent = 'Send to survey ▸';
    button.title = 'Send this plan to the ShieldLab survey below the drawing';
    button.setAttribute('style', [
      'position:fixed', 'right:14px', 'bottom:14px', 'z-index:9999', 'padding:10px 16px',
      'border:0', 'border-radius:8px', 'background:#0b6e4f', 'color:#fff',
      'font:600 14px system-ui,sans-serif', 'box-shadow:0 2px 8px rgba(0,0,0,.25)',
      'cursor:pointer'].join(';'));
    button.addEventListener('click', function () {
      post('streamlit:setComponentValue',
           { value: { plan: planToSend(), sent_at: Date.now() }, dataType: 'json' });
      button.textContent = 'Sent ✓';
      setTimeout(function () { button.textContent = 'Send to survey ▸'; }, 1600);
    });
    document.body.appendChild(button);
  }

  addButton();
  post('streamlit:componentReady', { apiVersion: 1 });
  post('streamlit:setFrameHeight', { height: height });
})();
