// Node.js Execution Template
const fs = require("fs");
const { execSync } = require("child_process");

const packages_to_install = []; // REPLACED_BY_EXECUTOR

function log(msg, level) {
    console.error(`[${level}] ${msg}`);
}

if (packages_to_install.length > 0) {
    log(`Installing packages: ${packages_to_install.join(", ")}`, "INFO");
    try {
        // Create package.json if needed or just install
        // Using --no-save to avoid package-lock updates, --no-audit for speed
        execSync(`npm install --no-save --no-audit ${packages_to_install.join(" ")}`, { stdio: "inherit" });
        packages_to_install.forEach((p) => console.error(`CODEPOST_AUTO_INSTALL_SUCCESS: ${p}`));
        log("✓ Packages installed", "INFO");
    } catch (e) {
        log(`Failed to install packages: ${e.message}`, "ERROR");
    }
}

log("<<<RESULT>>>", "SYSTEM");

// USER CODE BEGINS
try {
    // We wrap in a block or just execute.
    // Since we are concatenating, variables declared with const/let at top level might conflict if we were inside a function,
    // but we are top level.
    // FILLER_CODE
} catch (e) {
    console.error(e);
    process.exit(1);
}
