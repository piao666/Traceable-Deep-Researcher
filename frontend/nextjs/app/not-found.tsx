import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <Link href="/" className="mb-8 text-xl font-semibold text-teal-300">
        Traceable Deep Researcher
      </Link>
      <h1 className="mb-3 text-2xl font-semibold text-white">页面不存在</h1>
      <p className="mb-6 text-gray-400">页面地址可能有误，或内容已被移除。</p>
      <Link href="/" className="rounded-md bg-teal-600 px-5 py-2.5 text-white hover:bg-teal-700">
        返回首页
      </Link>
    </main>
  );
}
