export async function GET() {
  try {
    const res = await fetch("http://100.117.139.24:5001/shells", {
      cache: "no-store",
    });

    if (!res.ok) {
      throw new Error("Failed to fetch AAS shells");
    }

    const shells = await res.json();

    const assets = shells.map((shell: any) => ({
      id: shell.identification?.id || "",
      idShort: shell.idShort || "Unknown",
      AssetCategory: shell.category || "Product",
      Family: shell.idShort || "Unknown",
      Variant: "Default",
    }));

    return Response.json(assets);
  } catch (error) {
    console.error("Assets API error:", error);

    return Response.json({ error: "Failed to load assets" }, { status: 500 });
  }
}
