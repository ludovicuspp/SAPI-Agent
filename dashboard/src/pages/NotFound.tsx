export default function NotFound() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
      <h1 className="text-6xl font-bold text-gray-300">404</h1>
      <p className="mt-4 text-gray-500">Página no encontrada</p>
      <a href="/" className="mt-4 text-sm text-brand-600 hover:underline">Volver al inicio</a>
    </div>
  );
}
