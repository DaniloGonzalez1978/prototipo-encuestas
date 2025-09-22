
document.addEventListener('DOMContentLoaded', function() {

    // --- Contenedores de Pasos ---
    const steps = [document.getElementById('step1'), document.getElementById('step2'), document.getElementById('step3')];

    // --- Botones de Navegación ---
    const continueStep1Btn = document.getElementById('continue-step1');
    const prevStep2Btn = document.getElementById('prev-step2');
    const nextStep2Btn = document.getElementById('next-step2');
    const prevStep3Btn = document.getElementById('prev-step3');

    // --- Botones de Acción ---
    const validateRutBtn = document.getElementById('validate-rut-btn');
    const saveDataBtn = document.getElementById('save-data');

    // --- Elementos de UI ---
    const loader = document.getElementById('loader');
    const validationResultDiv = document.getElementById('validation-result');
    const progressBar = document.getElementById('progress-bar');
    
    // --- Inputs de archivos ---
    const fileUploadFrontInput = document.getElementById('file-upload-front');
    const fileCameraFrontInput = document.getElementById('file-camera-front');
    const fileUploadBackInput = document.getElementById('file-upload-back');
    const fileCameraBackInput = document.getElementById('file-camera-back');

    // --- Modal y Cropper ---
    const cropModalEl = document.getElementById('cropModal');
    const cropModal = new bootstrap.Modal(cropModalEl);
    const imageToCrop = document.getElementById('image-to-crop');
    const cropAndSaveBtn = document.getElementById('crop-and-save');
    let cropper;
    let currentCropSide = 'front'; // 'front' or 'back'
    let frontFile, backFile;

    // --- LÓGICA CENTRAL DE NAVEGACIÓN Y UI ---

    function showStep(stepIndex) {
        steps.forEach((step, index) => {
            if (step) step.style.display = (index === stepIndex) ? 'block' : 'none';
        });

        const progressPercentage = ((stepIndex + 1) / steps.length) * 100;
        progressBar.style.width = `${progressPercentage}%`;
        progressBar.textContent = `Paso ${stepIndex + 1} de ${steps.length}`;
        progressBar.setAttribute('aria-valuenow', progressPercentage);
        
        if (stepIndex === 2) progressBar.textContent = `Paso Final`;
    }

    function showAlert(placeholderId, message, type) {
        const placeholder = document.getElementById(placeholderId);
        if (!placeholder) return;
        const alertInfo = { success: { icon: 'bi-check-circle-fill', color: 'success' }, danger: { icon: 'bi-exclamation-triangle-fill', color: 'danger' }, warning: { icon: 'bi-exclamation-triangle-fill', color: 'warning' }, info: { icon: 'bi-info-circle-fill', color: 'info' } }[type] || { icon: 'bi-info-circle-fill', color: 'info' };
        placeholder.innerHTML = `<div class="alert alert-${alertInfo.color} alert-custom d-flex align-items-start shadow-sm" role="alert"><i class="bi ${alertInfo.icon} me-3 mt-1"></i><div style="white-space: pre-line;">${message}</div></div>`;
    }

    // --- EVENT LISTENERS DE NAVEGACIÓN ---
    if (continueStep1Btn) {
        continueStep1Btn.addEventListener('click', () => showStep(1));
        if (continueStep1Btn.disabled) showAlert('alert-no-units', 'Ya has completado la votación para todas tus unidades.', 'info');
    }
    if (prevStep2Btn) prevStep2Btn.addEventListener('click', () => showStep(0));
    if (nextStep2Btn) nextStep2Btn.addEventListener('click', () => showStep(2));
    if (prevStep3Btn) prevStep3Btn.addEventListener('click', () => showStep(1));

    // --- LÓGICA DE RECORTE Y VALIDACIÓN DE CÉDULA (Paso 2) ---

    function startCropper(event) {
        const file = event.target.files[0];
        if (!file) return;

        currentCropSide = event.target.id.includes('front') ? 'front' : 'back';

        const reader = new FileReader();
        reader.onload = (e) => {
            imageToCrop.src = e.target.result;
            cropModal.show();
        };
        reader.readAsDataURL(file);

        event.target.value = '';
    }

    cropModalEl.addEventListener('shown.bs.modal', () => {
        if (cropper) cropper.destroy();
        cropper = new Cropper(imageToCrop, {
            aspectRatio: 85.6 / 53.98,
            viewMode: 2,
            dragMode: 'move',
            background: false,
            autoCropArea: 0.9,
        });
    });

    if (cropAndSaveBtn) {
        cropAndSaveBtn.addEventListener('click', () => {
            const canvas = cropper.getCroppedCanvas({
                width: 856,
                height: 540,
                imageSmoothingQuality: 'high',
            });

            canvas.toBlob((blob) => {
                const fileName = currentCropSide === 'front' ? 'id_frontal_recortada.jpg' : 'id_trasera_recortada.jpg';
                const croppedFile = new File([blob], fileName, { type: 'image/jpeg', lastModified: Date.now() });
                
                const previewId = `preview-${currentCropSide}`;
                const preview = document.getElementById(previewId);

                if (currentCropSide === 'front') {
                    frontFile = croppedFile;
                } else {
                    backFile = croppedFile;
                }

                preview.src = URL.createObjectURL(croppedFile);
                preview.style.display = 'block';
                preview.classList.add('loaded');
                preview.onload = () => URL.revokeObjectURL(preview.src);

                // --- ÚNICO CAMBIO REALIZADO ---
                if (frontFile && backFile) validateRutBtn.disabled = false;
                
                cropModal.hide();
            }, 'image/jpeg', 0.9);
        });
    }

    [fileUploadFrontInput, fileCameraFrontInput, fileUploadBackInput, fileCameraBackInput].forEach(input => {
        if (input) input.addEventListener('change', startCropper);
    });

    if (validateRutBtn) {
        validateRutBtn.addEventListener('click', () => {
            if (!frontFile || !backFile) { // Se mantiene la doble verificación por seguridad
                showAlert('validation-result', 'Debes subir y recortar la imagen frontal y trasera de tu carnet.', 'warning');
                return;
            }

            loader.style.display = 'block';
            validationResultDiv.innerHTML = '';
            validateRutBtn.disabled = true;
            nextStep2Btn.disabled = true;

            const formData = new FormData();
            formData.append('id_frontal', frontFile);
            formData.append('id_trasera', backFile);

            fetch('/validate_rut', { method: 'POST', body: formData })
            .then(response => response.ok ? response.json() : response.json().then(err => { throw new Error(err.error || `Error: ${response.statusText}`) }))
            .then(data => {
                loader.style.display = 'none';
                if (data.success) {
                    if (data.rut_match) {
                        showAlert('validation-result', `✅ ¡Validación exitosa! El RUT de la imagen (${data.extracted_rut}) coincide con tu registro.`, 'success');
                        nextStep2Btn.disabled = false;
                    } else {
                        showAlert('validation-result', `⚠️ El RUT de la imagen (${data.extracted_rut}) no coincide con tu registro (${data.user_rut}). Por favor, intenta con una nueva  o ajusta el recorte de la imagen.`, 'warning');
                        validateRutBtn.disabled = false;
                    }
                } else {
                    showAlert('validation-result', `❌ Error: ${data.error}`, 'danger');
                    validateRutBtn.disabled = false;
                }
            })
            .catch(error => {
                loader.style.display = 'none';
                showAlert('validation-result', `❌ Error de conexión o servidor: ${error.message}. Inténtalo de nuevo.`, 'danger');
                validateRutBtn.disabled = false;
            });
        });
    }

    // --- LÓGICA DE GUARDADO FINAL (Paso 3) ---
    if (saveDataBtn) {
        saveDataBtn.addEventListener('click', () => {
            const selectedAnswer = document.querySelector('input[name="final-answer"]:checked');
            if (!selectedAnswer) {
                showAlert('final-result', 'Por favor, selecciona una opción.', 'warning');
                return;
            }

            saveDataBtn.disabled = true;
            saveDataBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando...';

            fetch('/save_data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ final_answer: selectedAnswer.value }) })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.href = '/';
                } else {
                    showAlert('final-result', data.error || 'Ocurrió un error inesperado.', 'danger');
                    saveDataBtn.disabled = false;
                    saveDataBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Guardar y Finalizar';
                }
            })
            .catch(error => {
                showAlert('final-result', 'Error de conexión. No se pudo guardar.', 'danger');
                saveDataBtn.disabled = false;
                saveDataBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Guardar y Finalizar';
            });
        });
    }

    showStep(0);
});
