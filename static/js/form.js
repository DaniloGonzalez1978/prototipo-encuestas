
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
    const fileUploadBackInput = document.getElementById('file-upload-back');
    const fileCameraFrontInput = document.getElementById('file-camera-front');
    const fileCameraBackInput = document.getElementById('file-camera-back');

    let frontFile, backFile;

    // --- LÓGICA CENTRAL DE NAVEGACIÓN Y UI ---

    function showStep(stepIndex) {
        steps.forEach((step, index) => {
            if (step) {
                step.style.display = (index === stepIndex) ? 'block' : 'none';
            }
        });

        const progressPercentage = ((stepIndex + 1) / steps.length) * 100;
        progressBar.style.width = `${progressPercentage}%`;
        progressBar.textContent = `Paso ${stepIndex + 1} de ${steps.length}`;
        progressBar.setAttribute('aria-valuenow', progressPercentage);
        
        if (stepIndex === 2) {
             progressBar.textContent = `Paso Final`;
        }
    }

    function showAlert(placeholderId, message, type) {
        const placeholder = document.getElementById(placeholderId);
        if (!placeholder) return;

        const alertTypes = {
            success: { icon: 'bi-check-circle-fill', color: 'success' },
            danger: { icon: 'bi-exclamation-triangle-fill', color: 'danger' },
            warning: { icon: 'bi-exclamation-triangle-fill', color: 'warning' },
            info: { icon: 'bi-info-circle-fill', color: 'info' }
        };

        const alertInfo = alertTypes[type] || alertTypes.info;
        
        placeholder.innerHTML = `
            <div class="alert alert-${alertInfo.color} alert-custom d-flex align-items-center shadow-sm" role="alert">
                <i class="bi ${alertInfo.icon} me-2"></i>
                <div>${message}</div>
            </div>`;
    }

    // --- EVENT LISTENERS DE NAVEGACIÓN ---

    if (continueStep1Btn) {
        continueStep1Btn.addEventListener('click', () => showStep(1));
        if (continueStep1Btn.disabled) {
            showAlert('alert-no-units', 'Ya has completado la votación para todas tus unidades.', 'info');
        }
    }

    if (prevStep2Btn) prevStep2Btn.addEventListener('click', () => showStep(0));
    if (nextStep2Btn) nextStep2Btn.addEventListener('click', () => showStep(2));
    if (prevStep3Btn) prevStep3Btn.addEventListener('click', () => showStep(1));

    
    // --- LÓGICA DE VALIDACIÓN DE CÉDULA (Paso 2) ---

    function handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        const isFront = event.target.id.includes('front');
        const previewId = isFront ? 'preview-front' : 'preview-back';
        const preview = document.getElementById(previewId);
        
        if (isFront) {
            frontFile = file;
        } else {
            backFile = file;
        }

        preview.src = URL.createObjectURL(file);
        preview.style.display = 'block';
        preview.onload = () => URL.revokeObjectURL(preview.src);

        // Habilitar el botón de validación solo si la imagen frontal está cargada.
        if (frontFile) {
            validateRutBtn.disabled = false;
        }
    }

    [fileUploadFrontInput, fileCameraFrontInput, fileUploadBackInput, fileCameraBackInput].forEach(input => {
        if (input) input.addEventListener('change', handleFileSelect);
    });

    if (validateRutBtn) {
        validateRutBtn.addEventListener('click', () => {
            if (!frontFile) {
                showAlert('validation-result', 'Debes subir al menos la imagen frontal de tu carnet.', 'warning');
                return;
            }

            loader.style.display = 'block';
            validationResultDiv.innerHTML = '';
            validateRutBtn.disabled = true;
            nextStep2Btn.disabled = true;

            const formData = new FormData();
            formData.append('id_frontal', frontFile);
            if (backFile) {
                formData.append('id_trasera', backFile);
            }

            // INICIO DEL CÓDIGO REAL
            fetch('/validate_rut', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    // Si la respuesta no es OK, intenta leer el JSON del error
                    return response.json().then(err => { throw new Error(err.error || `Error del servidor: ${response.statusText}`) });
                }
                return response.json();
            })
            .then(data => {
                loader.style.display = 'none';
                if (data.success) {
                    if (data.rut_match) {
                        showAlert('validation-result', `✅ ¡Validación exitosa! El RUT de la imagen (${data.extracted_rut}) coincide con tu registro.`, 'success');
                        nextStep2Btn.disabled = false; // Habilitar el botón para continuar
                    } else {
                        showAlert('validation-result', `⚠️ El RUT de la imagen (${data.extracted_rut}) no coincide con el RUT registrado (${data.user_rut}). Por favor, inténtalo de nuevo con una imagen más clara.`, 'warning');
                        validateRutBtn.disabled = false; // Permitir reintentar
                    }
                } else {
                    showAlert('validation-result', `❌ Error en la validación: ${data.error}`, 'danger');
                    validateRutBtn.disabled = false;
                }
            })
            .catch(error => {
                console.error('Error en la validación:', error);
                loader.style.display = 'none';
                showAlert('validation-result', `❌ Error de conexión o del servidor: ${error.message}. Inténtalo de nuevo.`, 'danger');
                validateRutBtn.disabled = false;
            });
            // FIN DEL CÓDIGO REAL
        });
    }

    // --- LÓGICA DE GUARDADO FINAL (Paso 3) ---

    if (saveDataBtn) {
        saveDataBtn.addEventListener('click', () => {
            const selectedAnswer = document.querySelector('input[name="final-answer"]:checked');
            if (!selectedAnswer) {
                showAlert('final-result', 'Por favor, selecciona una opción para el reglamento.', 'warning');
                return;
            }

            saveDataBtn.disabled = true;
            saveDataBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando...';

            fetch('/save_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ final_answer: selectedAnswer.value })
            })
            .then(response => response.json())
            .then(data => {
                const step3Body = document.querySelector('#step3 .card-body');
                const step3Footer = document.querySelector('#step3 .card-footer');
                const progressBarContainer = document.querySelector('.progress-container'); // Target a container

                if (data.success) {
                    if(progressBarContainer) progressBarContainer.style.display = 'none';
                    step3Body.innerHTML = '';
                    
                    // Crear un contenedor específico si no existe
                    let alertContainer = document.getElementById('step3-final-alert');
                    if (!alertContainer) {
                        alertContainer = document.createElement('div');
                        alertContainer.id = 'step3-final-alert';
                        step3Body.appendChild(alertContainer);
                    }

                    showAlert(alertContainer.id, data.message, 'success');
                    step3Footer.innerHTML = '<a href="/logout" class="btn btn-primary btn-lg w-100"><i class="bi bi-box-arrow-left"></i> Salir de la sesión</a>';
                } else {
                    showAlert('final-result', data.error || 'Ocurrió un error inesperado al guardar.', 'danger');
                    saveDataBtn.disabled = false;
                    saveDataBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Guardar y Finalizar';
                }
            })
            .catch(error => {
                console.error('Error en la solicitud Fetch:', error);
                showAlert('final-result', 'Error de conexión. No se pudo guardar tu voto.', 'danger');
                saveDataBtn.disabled = false;
                saveDataBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Guardar y Finalizar';
            });
        });
    }

    // Inicializar en el primer paso
    showStep(0);
});
