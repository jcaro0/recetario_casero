function createUnitSelector(id, active = () => true) {
    const element = byId("unitSelectorTemplate").content.firstElementChild.cloneNode(true);
    const select = element.querySelector("select");
    const custom = element.querySelector(".custom-unit");
    const customOption = select.options[select.options.length - 1];
    if (id) select.id = id;

    const validate = () => {
        custom.required = active() && !custom.disabled;
        custom.setCustomValidity(custom.required && !custom.value.trim() ? "Escribe una unidad." : "");
    };
    const updateMode = () => {
        custom.hidden = custom.disabled = select.selectedOptions[0] !== customOption;
        validate();
    };
    select.addEventListener("change", () => {
        updateMode();
        if (!custom.hidden) custom.focus();
    });
    custom.addEventListener("input", validate);

    return {
        element,
        validate,
        setValue(value = "") {
            const unit = value ?? "";
            const known = [...select.options].some(option => option !== customOption && option.value === unit);
            select.value = known ? unit : customOption.value;
            custom.value = known ? "" : unit;
            updateMode();
        },
        get value() {
            if (custom.disabled) return select.value;
            // Conserva el texto exacto de una unidad antigua si no se editó.
            return custom.value.trim() ? custom.value : "";
        }
    };
}
