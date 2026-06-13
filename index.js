document.addEventListener('DOMContentLoaded', () => {
    // Mode Switcher Elements
    const btnModeFile = document.getElementById('btn-mode-file');
    const btnModeText = document.getElementById('btn-mode-text');
    const fileUploadGroup = document.getElementById('file-upload-group');
    const rawTextGroup = document.getElementById('raw-text-group');

    // File input elements
    const dragZone = document.getElementById('drag-zone');
    const fileInput = document.getElementById('html-file-input');
    const selectedFilename = document.getElementById('selected-filename');

    // Advanced settings Accordion elements
    const advTrigger = document.getElementById('adv-options-trigger');
    const accordion = advTrigger.parentElement;

    // Form submission elements
    const compileForm = document.getElementById('compile-form');
    const btnSubmit = document.getElementById('btn-submit');
    const submitText = document.getElementById('submit-text');
    const submitLoader = document.getElementById('submit-loader');

    // Results elements
    const resultPanel = document.getElementById('result-panel');
    const codeOutput = document.getElementById('code-output');
    const statContainers = document.getElementById('stat-containers');
    const statWidgets = document.getElementById('stat-widgets');
    const btnCopy = document.getElementById('btn-copy');
    const btnDownload = document.getElementById('btn-download');

    let currentMode = 'file'; // 'file' or 'text'
    let compiledResultData = null;

    // 1. Toggle between modes
    btnModeFile.addEventListener('click', () => {
        currentMode = 'file';
        btnModeFile.classList.add('active');
        btnModeText.classList.remove('active');
        fileUploadGroup.classList.remove('hidden');
        rawTextGroup.classList.add('hidden');
    });

    btnModeText.addEventListener('click', () => {
        currentMode = 'text';
        btnModeText.classList.add('active');
        btnModeFile.classList.remove('active');
        rawTextGroup.classList.remove('hidden');
        fileUploadGroup.classList.add('hidden');
    });

    // 2. Drag and drop file upload
    dragZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dragZone.classList.add('dragover');
    });

    dragZone.addEventListener('dragleave', () => {
        dragZone.classList.remove('dragover');
    });

    dragZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dragZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            updateSelectedFilename();
        }
    });

    fileInput.addEventListener('change', () => {
        updateSelectedFilename();
    });

    function updateSelectedFilename() {
        if (fileInput.files.length > 0) {
            selectedFilename.textContent = `Selected: ${fileInput.files[0].name}`;
            selectedFilename.style.color = '#ffffff';
        } else {
            selectedFilename.textContent = 'Supported format: .html';
            selectedFilename.style.color = 'var(--text-muted)';
        }
    }

    // 3. Advanced Settings Accordion trigger
    advTrigger.addEventListener('click', () => {
        accordion.classList.toggle('open');
    });

    // 4. Form Submit & Compilation
    compileForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Validate
        if (currentMode === 'file' && fileInput.files.length === 0) {
            alert('Please select or drag an HTML file first.');
            return;
        }
        if (currentMode === 'text' && !document.getElementById('html-text-input').value.trim()) {
            alert('Please paste some HTML code first.');
            return;
        }

        // Prepare parameters
        const formData = new FormData();
        if (currentMode === 'file') {
            formData.append('html_file', fileInput.files[0]);
        } else {
            formData.append('html_text', document.getElementById('html-text-input').value);
        }

        const baseAssetUrlVal = document.getElementById('base-asset-url').value.trim();
        const wpUrlVal = document.getElementById('wp-url').value.trim();
        const wpUserVal = document.getElementById('wp-user').value.trim();
        const wpPassVal = document.getElementById('wp-pass').value.trim();

        if (baseAssetUrlVal) formData.append('base_asset_url', baseAssetUrlVal);
        if (wpUrlVal) formData.append('wp_url', wpUrlVal);
        if (wpUserVal) formData.append('wp_user', wpUserVal);
        if (wpPassVal) formData.append('wp_pass', wpPassVal);

        // Show Loader
        btnSubmit.disabled = true;
        submitText.textContent = 'Compiling template...';
        submitLoader.classList.remove('hidden');
        resultPanel.classList.add('hidden');

        try {
            const response = await fetch('/api/compile', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Compilation failed');
            }

            const data = await response.json();
            compiledResultData = data;

            // Render stats
            let containersCount = 0;
            let widgetsCount = 0;
            function countElements(elements) {
                elements.forEach(el => {
                    if (el.elType === 'container') containersCount++;
                    else if (el.elType === 'widget') widgetsCount++;
                    if (el.elements && el.elements.length > 0) {
                        countElements(el.elements);
                    }
                });
            }
            if (data.content) {
                countElements(data.content);
            }
            statContainers.textContent = `${containersCount} Containers`;
            statWidgets.textContent = `${widgetsCount} Widgets`;

            // Display code output
            codeOutput.textContent = JSON.stringify(data, null, 4);

            // Display Results
            resultPanel.classList.remove('hidden');
            resultPanel.scrollIntoView({ behavior: 'smooth' });

        } catch (err) {
            console.error(err);
            alert(`Error: ${err.message}`);
        } finally {
            // Restore Button
            btnSubmit.disabled = false;
            submitText.textContent = 'Compile HTML Template';
            submitLoader.classList.add('hidden');
        }
    });

    // 5. Copy JSON Action
    btnCopy.addEventListener('click', () => {
        if (!compiledResultData) return;
        navigator.clipboard.writeText(JSON.stringify(compiledResultData, null, 4))
            .then(() => {
                const originalText = btnCopy.textContent;
                btnCopy.textContent = '✓ Copied!';
                btnCopy.style.color = 'var(--success)';
                setTimeout(() => {
                    btnCopy.textContent = originalText;
                    btnCopy.style.color = '#ffffff';
                }, 2000);
            })
            .catch(err => {
                console.error('Failed to copy text: ', err);
            });
    });

    // 6. Download JSON Template Action
    btnDownload.addEventListener('click', () => {
        if (!compiledResultData) return;
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(compiledResultData, null, 4));
        const downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute("href", dataStr);
        downloadAnchor.setAttribute("download", "elementor-template.json");
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        downloadAnchor.remove();
    });
});
