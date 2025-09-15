document.addEventListener('DOMContentLoaded', function() {
    console.log("El script externo form.js se ha cargado.");

    let currentStep = 1;
    let rutValidationResult = {}; // Almacena el resultado de la validación
    let validationStartTime;

    // --- Funciones de Navegación ---
    function showStep(step) {
        document.querySelectorAll('.step-container').forEach(el => el.classList.remove('active'));
        const stepToShow = document.getElementById(`step${step}`);
        if (stepToShow) {
            stepToShow.classList.add('active');
        }
    }

    function nextStep() {
        if (currentStep < 3) {
            currentStep++;
            showStep(currentStep);
        }
    }

    function prevStep() {
        if (currentStep > 1) {
            currentStep--;
            showStep(currentStep);
        }
    }

    // --- Asignación de Eventos de Navegación ---
    document.getElementById('continue-step1').addEventListener('click', nextStep);
    document.getElementById('prev-step2').addEventListener('click', prevStep);
    document.getElementById('next-step2').addEventListener('click', nextStep);
    document.getElementById('prev-step3').addEventListener('click', prevStep);

    // --- Lógica del Paso 2: Validación de Cédula ---
    const fileUploadFront = document.getElementById('file-upload-front');
    const fileUploadBack = document.getElementById('file-upload-back');
    const previewFront = document.getElementById('preview-front');
    const previewBack = document.getElementById('preview-back');
    const validateRutBtn = document.getElementById('validate-rut-btn');
    const nextStep2Btn = document.getElementById('next-step2');

    function showPreview(input, previewElement) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function(e) {
                previewElement.src = e.target.result;
                previewElement.style.display = 'block';
                previewElement.classList.add('loaded'); // Añadir clase para feedback visual
            };
            reader.readAsDataURL(input.files[0]);
        }
    }

    function checkFiles() {
        if (fileUploadFront.files.length > 0 && fileUploadBack.files.length > 0) {
            validateRutBtn.disabled = false;
        } else {
            validateRutBtn.disabled = true;
        }
    }

    fileUploadFront.addEventListener('change', () => { 
        showPreview(fileUploadFront, previewFront);
        checkFiles();
    });
    fileUploadBack.addEventListener('change', () => {
        showPreview(fileUploadBack, previewBack);
        checkFiles();
    });

    validateRutBtn.addEventListener('click', async () => {
        if (fileUploadFront.files.length === 0) {
            alert('Por favor, sube la imagen frontal de tu cédula.');
            return;
        }

        const formData = new FormData();
        formData.append('file_front', fileUploadFront.files[0]);
        formData.append('file_back', fileUploadBack.files[0]);

        document.getElementById('loader').style.display = 'block';
        document.getElementById('validation-result').innerHTML = '';
        validateRutBtn.disabled = true;
        validationStartTime = new Date();

        // Reset visual feedback
        previewFront.classList.remove('loaded');
        previewBack.classList.remove('loaded');
        nextStep2Btn.disabled = true;

        try {
            const response = await fetch('/upload', { method: 'POST', body: formData });
            const result = await response.json();
            
            if (result.redirect) {
                window.location.href = result.redirect;
                return;
            }
            
            rutValidationResult = result;
            rutValidationResult.validation_duration = (new Date() - validationStartTime) / 1000;

            const resultDiv = document.getElementById('validation-result');
            if (result.success) {
                let alertClass = result.match ? 'alert-success' : 'alert-danger';
                resultDiv.innerHTML = `<div class="alert ${alertClass}"><b>Resultado:</b> ${result.message}</div>`;
                
                if (result.image_front_url) {
                    previewFront.src = result.image_front_url + '?t=' + new Date().getTime();
                }

                if (result.match) {
                    nextStep2Btn.disabled = false;
                } else {
                    // Si no hay match, permitir al usuario intentarlo de nuevo
                    validateRutBtn.disabled = false;
                }
            } else {
                resultDiv.innerHTML = `<div class="alert alert-danger">${result.error}</div>`;
                // Permitir al usuario intentarlo de nuevo si hay un error
                validateRutBtn.disabled = false;
            }
        } catch (error) {
            document.getElementById('validation-result').innerHTML = `<div class="alert alert-danger">Error de conexión al intentar validar.</div>`;
            validateRutBtn.disabled = false;
        } finally {
            document.getElementById('loader').style.display = 'none';
        }
    });

    // --- Lógica del Paso 3: Guardado Final ---
    document.getElementById('save-data').addEventListener('click', async () => {
        const finalAnswer = document.querySelector('input[name="final-answer"]:checked').value;
        
        const finalData = {
            ...rutValidationResult,
            final_answer: finalAnswer,
        };

        document.getElementById('final-loader').style.display = 'block';

        try {
            const response = await fetch('/save_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(finalData)
            });
            const result = await response.json();
            
            const resultDiv = document.getElementById('final-result');
            if (result.success) {
                resultDiv.innerHTML = `<div class="alert alert-success">¡Gracias! Tu participación ha sido guardada con éxito.</div>`;
                document.getElementById('save-data').disabled = true;
                document.getElementById('prev-step3').style.display = 'none';
                 // Deshabilitar radios
                document.querySelectorAll('input[name="final-answer"]').forEach(radio => radio.disabled = true);
            } else {
                resultDiv.innerHTML = `<div class="alert alert-danger">${result.error}</div>`;
            }
        } catch (error) {
            document.getElementById('final-result').innerHTML = `<div class="alert alert-danger">Error de conexión al guardar los datos.</div>`;
        } finally {
            document.getElementById('final-loader').style.display = 'none';
        }
    });

    // Inicia en el primer paso
    showStep(currentStep);
});