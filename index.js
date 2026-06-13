document.addEventListener('DOMContentLoaded', () => {
    // File inputs & Drag Zone Elements
    const dragZone = document.getElementById('drag-zone');
    const fileInput = document.getElementById('html-file-input');
    const fileIndicator = document.getElementById('file-indicator');
    const selectedFilename = document.getElementById('selected-filename');
    const btnClearFile = document.getElementById('btn-clear-file');
    const rawTextInput = document.getElementById('html-text-input');

    // Advanced settings Accordion
    const advOptionsTrigger = document.getElementById('adv-options-trigger');
    const advConfigCard = document.getElementById('adv-config-card');

    // Action button & Loader
    const compileForm = document.getElementById('compile-form');
    const btnSubmit = document.getElementById('btn-submit');
    const submitText = document.getElementById('submit-text');
    const submitLoader = document.getElementById('submit-loader');

    // Output panel Elements
    const emptyState = document.getElementById('empty-state');
    const outputWindow = document.getElementById('output-window');
    const codeOutput = document.getElementById('code-output');
    const outputStats = document.getElementById('output-stats');
    const outputActions = document.getElementById('output-actions');
    const statContainers = document.getElementById('stat-containers');
    const statWidgets = document.getElementById('stat-widgets');
    
    // Output action buttons
    const btnCopy = document.getElementById('btn-copy');
    const btnDownload = document.getElementById('btn-download');

    let compiledResultData = null;

    // 1. Drag & Drop File Upload handling
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
            handleFileSelection();
        }
    });

    fileInput.addEventListener('change', () => {
        handleFileSelection();
    });

    btnClearFile.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.value = '';
        handleFileSelection();
    });

    function handleFileSelection() {
        if (fileInput.files.length > 0) {
            selectedFilename.textContent = fileInput.files[0].name;
            fileIndicator.classList.remove('hidden');
            dragZone.classList.add('hidden');
            rawTextInput.disabled = true; // disable text input since file is selected
            rawTextInput.placeholder = "File selected above. Clear file to write HTML manually.";
        } else {
            selectedFilename.textContent = '';
            fileIndicator.classList.add('hidden');
            dragZone.classList.remove('hidden');
            rawTextInput.disabled = false;
            rawTextInput.placeholder = "<!-- Paste your raw HTML here... -->";
        }
    }

    // 2. Advanced settings collapsible triggers
    advOptionsTrigger.addEventListener('click', () => {
        advConfigCard.classList.toggle('open');
    });

    // 3. Compile Form Submission
    compileForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const hasFile = fileInput.files.length > 0;
        const htmlCode = rawTextInput.value.trim();

        if (!hasFile && !htmlCode) {
            alert('Please upload an HTML file or paste raw HTML code to compile.');
            return;
        }

        // Prepare request payload
        const formData = new FormData();
        if (hasFile) {
            formData.append('html_file', fileInput.files[0]);
        } else {
            formData.append('html_text', htmlCode);
        }

        // Advanced Option values
        const baseAssetUrlVal = document.getElementById('base-asset-url').value.trim();
        const wpUrlVal = document.getElementById('wp-url').value.trim();
        const wpUserVal = document.getElementById('wp-user').value.trim();
        const wpPassVal = document.getElementById('wp-pass').value.trim();

        if (baseAssetUrlVal) formData.append('base_asset_url', baseAssetUrlVal);
        if (wpUrlVal) formData.append('wp_url', wpUrlVal);
        if (wpUserVal) formData.append('wp_user', wpUserVal);
        if (wpPassVal) formData.append('wp_pass', wpPassVal);

        // UI Loading States
        btnSubmit.disabled = true;
        submitText.textContent = 'Compiling...';
        submitLoader.classList.remove('hidden');

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

            // Compute statistics
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

            // Render stats
            statContainers.textContent = `${containersCount} Container${containersCount !== 1 ? 's' : ''}`;
            statWidgets.textContent = `${widgetsCount} Widget${widgetsCount !== 1 ? 's' : ''}`;

            // Set JSON output code
            codeOutput.textContent = JSON.stringify(data, null, 4);

            // Toggle panels display
            emptyState.classList.add('hidden');
            outputWindow.classList.remove('hidden');
            outputStats.classList.remove('hidden');
            outputActions.classList.remove('hidden');

        } catch (err) {
            console.error(err);
            alert(`Error: ${err.message}`);
        } finally {
            // Restore button trigger states
            btnSubmit.disabled = false;
            submitText.textContent = 'Compile Layout';
            submitLoader.classList.add('hidden');
        }
    });

    // 4. Copy Output Action
    btnCopy.addEventListener('click', () => {
        if (!compiledResultData) return;
        navigator.clipboard.writeText(JSON.stringify(compiledResultData, null, 4))
            .then(() => {
                const prevText = btnCopy.textContent;
                btnCopy.textContent = 'Copied';
                btnCopy.style.borderColor = 'var(--success)';
                btnCopy.style.color = 'var(--success)';
                setTimeout(() => {
                    btnCopy.textContent = prevText;
                    btnCopy.style.borderColor = 'var(--border)';
                    btnCopy.style.color = 'var(--text)';
                }, 2000);
            })
            .catch(err => {
                console.error('Clipboard copy failed: ', err);
            });
    });

    // 5. Download Template Action
    btnDownload.addEventListener('click', () => {
        if (!compiledResultData) return;
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(compiledResultData, null, 4));
        const downloadLink = document.createElement('a');
        downloadLink.setAttribute("href", dataStr);
        downloadLink.setAttribute("download", "elementor-template.json");
        document.body.appendChild(downloadLink);
        downloadLink.click();
        downloadLink.remove();
    });
});
