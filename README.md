# Plant Web Prototype — React + Supabase Auth

A small standalone web starter. Features include email/password signup and login, email-confirmation support, forgot/reset password, protected dashboard, logout, and leaf-image preview. The AI inference pipeline is **not connected yet**; no fake disease results are generated.

## 1. Extract into your empty local folder

`E:\Major Project\PLANT_WEB_PROTOTYPE`

The ZIP contains files directly at the root. Do **not** extract into `PLANT_DISEASE_PLATFORM`; leave your old Git project and original model files untouched.

## 2. Configure your key

In PowerShell, run from the new folder:

```powershell
Copy-Item .env.example .env.local
notepad .env.local
```

Your URL is already in the template. Replace `PASTE_YOUR_SB_PUBLISHABLE_KEY_HERE` with your **default Publishable Key** (starts `sb_publishable_`). Never place an `sb_secret_` key, a legacy `service_role` key, or database password in frontend environment variables.

## 3. Set your Supabase redirect URLs

Supabase dashboard > Authentication > URL Configuration:

- Site URL: `http://localhost:5173`
- Additional Redirect URLs: `http://localhost:5173/**`

You may need to confirm email after signup. Supabase's default email provider has sending limits. For testing use an inbox you control.

## 4. Run the app

```powershell
cd 'E:\Major Project\PLANT_WEB_PROTOTYPE'
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

## 5. Test

1. Register using your own email and password.
2. If confirmation is required, check your inbox and click the verification link. Email delivery can take time or be rate-limited by Supabase.
3. Sign in; verify the dashboard appears.
4. Upload a JPG/PNG/WebP photo (max 10 MB), and check preview.
5. Log out.
6. Optionally test password reset via email.

## Notes

- The image remains in browser memory only. It is **not** uploaded or analyzed yet.
- There is no database schema, analysis history, or FastAPI integration in this step.
- Browser publishable keys are designed to be public. Protect any future database with RLS and never expose admin/secret keys.
- The original trained checkpoints remain outside this folder and are never changed.
