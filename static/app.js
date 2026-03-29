/**
 * Credit-my-CC — Client-side logic.
 *
 * Handles: filename lookup via /api/lookup, letter generation via
 * /api/letter, and clipboard copy.
 */

document.addEventListener("DOMContentLoaded", () => {
    const $  = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ── Elements ──────────────────────────────────────────────────────
    const filenameInput   = $("#filename");
    const btnCheck        = $("#btn-check");
    const thumbWrap       = $("#thumb-wrap");
    const thumbImg        = $("#thumb-img");
    const thumbLink       = $("#thumb-link");
    const status          = $("#status");
    const postLookup      = $("#post-lookup");
    const btnWrite        = $("#btn-write");
    const letterSection   = $("#letter-section");
    const letterContent   = $("#letter-content");
    const langSelect      = $("#lang-select");
    const btnCopy         = $("#btn-copy");

    // ── Language switcher ─────────────────────────────────────────────
    langSelect.addEventListener("change", () => {
        const url = new URL(window.location);
        url.searchParams.set("lang", langSelect.value);
        window.location = url.toString();
    });

    // ── Auto-lookup if ?filename= is in URL ───────────────────────────
    const urlParams = new URLSearchParams(window.location.search);
    const urlFilename = urlParams.get("filename");
    if (urlFilename) {
        filenameInput.value = urlFilename;
        doLookup();
    }

    // ── Lookup button / Enter key ─────────────────────────────────────
    btnCheck.addEventListener("click", doLookup);
    filenameInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") doLookup();
    });

    // ── Write button ──────────────────────────────────────────────────
    btnWrite.addEventListener("click", doWrite);

    // ── Live previews for credit & description fields ─────────────────
    $$("#credit, #descr").forEach((input) => {
        input.addEventListener("input", () => {
            const previewEl = $(`#${input.id}-preview`);
            if (previewEl) previewEl.textContent = input.value;
        });
    });

    // ── "Other letters" dropdown toggle ────────────────────────────────
    const otherSelect = $("#other-letter-select");
    if (otherSelect) {
        $$("input[name='tone']").forEach((radio) => {
            radio.addEventListener("change", () => {
                otherSelect.classList.toggle("hidden", radio.value !== "other" || !radio.checked);
            });
        });
    }

    // ── Ctrl+C / ⌘+C auto-select letter ──────────────────────────────
    document.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "c") {
            if (!letterContent.textContent) return;
            if (window.getSelection().toString()) return;
            const range = document.createRange();
            range.selectNodeContents(letterContent);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        }
    });

    // ── Copy button ──────────────────────────────────────────────────
    btnCopy.addEventListener("click", () => {
        if (!letterContent.textContent) return;

        const htmlBlob = new Blob([letterContent.innerHTML], { type: "text/html" });
        const textBlob = new Blob([letterContent.innerText], { type: "text/plain" });

        if (navigator.clipboard?.write) {
            navigator.clipboard.write([
                new ClipboardItem({ "text/html": htmlBlob, "text/plain": textBlob }),
            ]).then(() => {
                showCopiedFeedback();
            }).catch(() => {
                fallbackCopy();
            });
        } else {
            fallbackCopy();
        }
    });

    function showCopiedFeedback() {
        btnCopy.textContent = MESSAGES.copied;
    }

    function fallbackCopy() {
        const range = document.createRange();
        range.selectNodeContents(letterContent);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand("copy");
        sel.removeAllRanges();
        showCopiedFeedback();
    }

    // ──────────────────────────────────────────────────────────────────
    // Lookup logic
    // ──────────────────────────────────────────────────────────────────

    function doLookup() {
        // Reset
        status.innerHTML = "";
        status.className = "status-message";
        thumbWrap.classList.add("hidden");
        postLookup.classList.add("hidden");
        letterSection.classList.add("hidden");

        const filename = filenameInput.value.trim();
        if (!filename) {
            filenameInput.classList.add("highlighted");
            return;
        }
        filenameInput.classList.remove("highlighted");

        const savedText = btnCheck.textContent;
        btnCheck.textContent = MESSAGES.loading;
        btnCheck.disabled = true;

        fetch(`/api/lookup?filename=${encodeURIComponent(filename)}&lang=${CURRENT_LANG}`)
            .then((r) => r.json())
            .then((data) => {
                btnCheck.textContent = savedText;
                btnCheck.disabled = false;
                handleLookupResult(data);
            })
            .catch(() => {
                btnCheck.textContent = savedText;
                btnCheck.disabled = false;
                showError(MESSAGES.missing_file);
            });
    }

    function handleLookupResult(data) {
        // Show thumbnail if available
        if (data.thumb_url) {
            thumbImg.src = data.thumb_url;
            thumbLink.href = data.description_url || "#";
            thumbWrap.classList.remove("hidden");
        }

        // Handle errors from the API
        if (data.error) {
            let msg = MESSAGES[data.error] || data.error;
            if (data.error === "api_error") {
                msg += ` (${data.error})`;
            }
            showError(msg);
            return;
        }

        // Populate the form
        $("#pagename-link").href = data.description_url;
        $("#pagename-link").textContent = data.file_title;
        $("#license-link").href = data.license_url;
        $("#license-link").textContent = data.license_title;
        $("#license_title").value = data.license_title;
        $("#license_url").value = data.license_url;
        $("#file_title").value = data.file_title;
        $("#file_url").value = data.description_url;
        $("#upload_date").value = data.upload_date || "";
        $("#credit").value = data.credit || "";
        $("#credit-preview").innerHTML = DOMPurify.sanitize(data.credit || "");
        $("#credit-extra").innerHTML = DOMPurify.sanitize(data.credit_extra || "");
        $("#descr").value = "";
        $("#descr-preview").textContent = "";
        $("#descr-extra").innerHTML = DOMPurify.sanitize(data.description_extra || "");
        $("#upload-date-note").textContent = data.upload_date ? MESSAGES.upload_date_note : "";

        postLookup.classList.remove("hidden");
        $("#usage").focus();
    }

    function showError(msg) {
        status.innerHTML = DOMPurify.sanitize(msg);
        status.className = "status-message error";
    }

    // ──────────────────────────────────────────────────────────────────
    // Write letter logic
    // ──────────────────────────────────────────────────────────────────

    function doWrite() {
        status.innerHTML = "";

        // Validate required fields
        const required = ["usage", "credit", "license_title", "license_url", "file_title", "file_url"];
        let missing = [];
        for (const id of required) {
            const el = $(`#${id}`);
            if (!el.value.trim()) {
                el.classList.add("warning");
                missing.push(id);
            } else {
                el.classList.remove("warning");
            }
        }
        if (missing.length) {
            showError(MESSAGES.missing_parameter + missing.join(", "));
            return;
        }

        let tone = document.querySelector("input[name='tone']:checked").value;
        if (tone === "other" && otherSelect) {
            tone = otherSelect.value;
        }

        const params = new URLSearchParams({
            tone,
            lang: CURRENT_LANG,
            credit: $("#credit").value,
            descr: $("#descr").value,
            file_url: $("#file_url").value,
            file_title: $("#file_title").value,
            license_title: $("#license_title").value,
            license_url: $("#license_url").value,
            upload_date: $("#upload_date").value,
            usage: $("#usage").value,
        });

        fetch(`/api/letter?${params.toString()}`)
            .then((r) => r.text())
            .then((html) => {
                letterContent.innerHTML = DOMPurify.sanitize(html);
                btnCopy.textContent = MESSAGES.copy;
                letterSection.classList.remove("hidden");
                letterSection.scrollIntoView({ behavior: "smooth" });
            })
            .catch(() => {
                showError("Failed to generate letter.");
            });
    }
});
