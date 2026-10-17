
// src/config/branding.ts

interface BrandingConfig {
  appName: string;
  companyNameForInvoice: string; // Added for clarity in invoice
  companyAddressForInvoice: string;
  companyPhoneForInvoice: string;
  companyWebsiteForInvoice?: string;
  logoPath: string; // Relative to /public directory
  faviconPath: string; // Relative to /public directory
  returnPolicyNotes?: string[]; // For Return/Exchange Policy
}

export const brandingConfig: BrandingConfig = {
  appName: "Retail Genie",
  companyNameForInvoice: "Retail Genie Solutions", // Or your preferred default
  companyAddressForInvoice: "Muscat, Oman",
  companyPhoneForInvoice: "+968-94700685",
  companyWebsiteForInvoice: "www.retailgenie.example", // Optional
  logoPath: "/assets/logo.svg",
  faviconPath: "/assets/favicon.svg",
  returnPolicyNotes: [
    "Items can be returned or exchanged within 7 days of purchase with the original receipt.",
    "Items must be in their original condition and packaging.",
    "No returns or exchanges on discounted or special order items.",
  ],
};
