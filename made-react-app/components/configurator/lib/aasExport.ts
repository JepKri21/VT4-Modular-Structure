import type { CapabilityEntry, Scene, TypeById, ZoneType } from "./types";

const LINE_CONFIG_ID =
  "https://aausmartlab.org/Shells/Configuration/ProductionLine1-12345678";

type SME = Record<string, unknown>;

const prop = (idShort: string, value: string | number, valueType: string): SME => ({
  idShort,
  modelType: "Property",
  value: typeof value === "number" ? String(value) : value,
  valueType,
});

const smc = (idShort: string, value: SME[]): SME => ({
  idShort,
  modelType: "SubmodelElementCollection",
  value,
});

const modelRef = (idShort: string, shellIri: string): SME => ({
  idShort,
  modelType: "ReferenceElement",
  value: {
    type: "ModelReference",
    keys: [{ type: "AssetAdministrationShell", value: shellIri }],
  },
});

const floatStr = (n: number): string => {
  const rounded = Math.round(n * 1000) / 1000;
  return Number.isInteger(rounded) ? `${rounded}.0` : String(rounded);
};

const zoneTypeToExport = (t: ZoneType): string =>
  t === "inout" ? "in_outfeed" : t;

const globalLocation = (x: number, y: number, theta?: number): SME => {
  const values: SME[] = [
    prop("XPos", floatStr(x), "xs:float"),
    prop("YPos", floatStr(y), "xs:float"),
  ];
  if (theta !== undefined) {
    values.push(prop("ThetaAngle", String(Math.round(theta)), "xs:integer"));
  }
  return smc("GlobalLocation", values);
};

const localLocation = (x: number, y: number): SME =>
  smc("LocalLocation", [
    prop("XPos", floatStr(x), "xs:float"),
    prop("YPos", floatStr(y), "xs:float"),
  ]);

export const buildLineConfigurationSubmodel = (
  submodelId: string = LINE_CONFIG_ID,
  scene: Scene,
  typeById: TypeById,
): Record<string, unknown> => {
  const resourceLocations = smc(
    "ResourceLocations",
    scene.resources.map((r) => {
      const type = typeById[r.typeId];
      return smc(type.name, [
        modelRef("ResourceReference", r.typeId),
        globalLocation(r.position.x, r.position.y, r.rotation),
      ]);
    }),
  );

  const connectionPoints = smc(
    "ConnectionPoints",
    scene.connections.map((c, i) => {
      const resA = scene.resources.find((r) => r.instanceId === c.resourceAId);
      const resB = scene.resources.find((r) => r.instanceId === c.resourceBId);
      const refA = resA ? resA.typeId : "";
      const refB = resB ? resB.typeId : "";
      return smc(`ConnectionPoint${i + 1}`, [
        globalLocation(c.worldPosition.x, c.worldPosition.y),
        smc("ConnectedResources", [
          smc("Resource1", [
            modelRef("ResourceReference", refA),
            prop("ZoneType", zoneTypeToExport(c.zoneAType), "xs:string"),
            localLocation(c.localPositionA.x, c.localPositionA.y),
          ]),
          smc("Resource2", [
            modelRef("ResourceReference", refB),
            prop("ZoneType", zoneTypeToExport(c.zoneBType), "xs:string"),
            localLocation(c.localPositionB.x, c.localPositionB.y),
          ]),
        ]),
      ]);
    }),
  );

  return {
    idShort: "LineConfiguration",
    modelType: "Submodel",
    id: submodelId,
    submodelElements: [resourceLocations, connectionPoints],
  };
};

export const buildServiceOfferedSubmodel = (
  submodelId: string,
  capabilities: CapabilityEntry[],
): Record<string, unknown> => {
  const entries = capabilities.map((cap, i) =>
    smc(`${cap.capabilityType}_${i}`, [
      prop("CapabilityType", cap.capabilityType, "xs:string"),
      prop("ResourceReference", cap.resourceRef, "xs:string"),
      prop("CapabilityReference", cap.capabilityRef, "xs:string"),
    ]),
  );
  return {
    idShort: "ServiceOffered",
    modelType: "Submodel",
    id: submodelId,
    submodelElements: [smc("OfferedCapabilities", entries)],
  };
};

export const exportLineConfiguration = (
  scene: Scene,
  typeById: TypeById,
): void => {
  const payload = buildLineConfigurationSubmodel(LINE_CONFIG_ID, scene, typeById);
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `line-configuration-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
};
