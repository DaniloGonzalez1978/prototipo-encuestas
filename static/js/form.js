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

    // --- LÓGICA CENTRAL DE NAVEGACIÓN Y UI ---

    function showStep(stepIndex) {
        // Oculta todos los pasos y muestra solo el activo, sin transiciones
        steps.forEach((step, index) => {
            if (step) {
                if (index === stepIndex) {
                    step.classList.add('active');
                } else {
                    step.classList.remove('active');
                }
            }
        });

        // Actualizar barra de progreso
        const progressPercentage = ((stepIndex + 1) / steps.length) * 100;
        progressBar.style.width = `${progressPercentage}%`;
        progressBar.textContent = `Paso ${stepIndex + 1} de ${steps.length}`;
        progressBar.setAttribute('aria-valuenow', progressPercentage);

        if (stepIndex === 2) { // Si es el último paso
             progressBar.textContent = `Completado`;
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
                <i class="bi ${alertInfo.icon}"></i>
                <div>${message}</div>
            </div>`;
    }


    // --- EVENT LISTENERS DE NAVEGACIÓN ---

    if (continueStep1Btn) {
        continueStep1Btn.addEventListener('click', () => showStep(1));

        // Si el botón está deshabilitado al cargar, mostrar alerta
        if (continueStep1Btn.disabled) {
            showAlert('alert-no-units', 'No tiene unidades pendientes de votación.', 'info');
        }
    }

    if (prevStep2Btn) prevStep2Btn.addEventListener('click', () => showStep(0));
    if (nextStep2Btn) nextStep2Btn.addEventListener('click', () => showStep(2));
    if (prevStep3Btn) prevStep3Btn.addEventListener('click', () => showStep(1));

    
    // --- LÓGICA DE VALIDACIÓN DE CÉDULA (Paso 2) ---

    function handleFilePreview(event) {
        const file = event.target.files[0];
        if (!file) return;

        const side = event.target.id.includes('front') ? 'front' : 'back';
        const preview = document.getElementById(`preview-${side}`);
        
        preview.src = URL.createObjectURL(file);
        preview.style.display = 'block';
        preview.onload = () => URL.revokeObjectURL(preview.src);
        preview.classList.add('loaded');

        const frontLoaded = document.getElementById('preview-front').classList.contains('loaded');
        const backLoaded = document.getElementById('preview-back').classList.contains('loaded');
        
        if (frontLoaded && backLoaded) {
            validateRutBtn.disabled = false;
        }
    }

    ['file-upload-front', 'file-camera-front', 'file-upload-back', 'file-camera-back'].forEach(id => {
        const input = document.getElementById(id);
        if (input) input.addEventListener('change', handleFilePreview);
    });

    if (validateRutBtn) {
        validateRutBtn.addEventListener('click', () => {
            loader.style.display = 'block';
            validationResultDiv.innerHTML = '';
            validateRutBtn.disabled = true;

            setTimeout(() => {
                loader.style.display = 'none';
                showAlert('validation-result', 'RUT validado correctamente.', 'success');
                nextStep2Btn.disabled = false;
            }, 1500);
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

            fetch('/save_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ final_answer: selectedAnswer.value })
            })
            .then(response => response.json())
            .then(data => {
                const step3Body = document.querySelector('#step3 .card-body');
                const step3Footer = document.querySelector('#step3 .card-footer');
                const progressBarContainer = document.querySelector('.progress');

                if (data.success) {
                    // 1. Ocultar barra de progreso y cuerpo del formulario
                    progressBarContainer.style.display = 'none';
                    step3Body.innerHTML = '';

                    // 2. Mostrar el mensaje de agradecimiento final
                    showAlert('step3 .card-body', data.message, 'success');

                    // 3. Cambiar los botones del footer
                    step3Footer.innerHTML = '<a href="/logout" class="btn btn-primary btn-lg w-100"><i class="bi bi-box-arrow-left"></i> Salir</a>';
                } else {
                    showAlert('final-result', data.error || 'Ocurrió un error inesperado.', 'danger');
                    saveDataBtn.disabled = false;
                    saveDataBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Guardar y Finalizar';
                }
            })
            .catch(error => {
                console.error('Error en la solicitud Fetch:', error);
                showAlert('final-result', 'Error de conexión. No se pudo guardar el voto.', 'danger');
                saveDataBtn.disabled = false;
                saveDataBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Guardar y Finalizar';
            });
        });
    }
});
